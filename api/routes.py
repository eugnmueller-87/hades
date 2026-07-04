import csv
import io
import logging
import os
import re
import threading
import time
from fastapi import APIRouter, Depends, HTTPException, Path, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from agent.graph import dd_graph
from api.auth import require_api_key
from integrations.hermes_client import HermesClient

# Public router — no auth. Only /health lives here (Railway healthcheck must
# not require a key).
public_router = APIRouter()

# Protected router — every route requires a valid X-API-Key (no-op when auth
# is disabled). Attaching the dependency here means any endpoint added later
# is protected by default.
router = APIRouter(dependencies=[Depends(require_api_key)])

logger = logging.getLogger("hades.api")

_hermes: HermesClient | None = None
_hermes_lock = threading.Lock()


def _get_hermes() -> HermesClient:
    global _hermes
    if _hermes is None:
        with _hermes_lock:
            if _hermes is None:
                _hermes = HermesClient()
    return _hermes


# --- Lightweight in-memory rate limit for /investigate (it calls paid APIs) ---
# Per-process fixed window keyed by client IP. Best-effort: resets on restart,
# X-Forwarded-For is spoofable — real abuse protection needs an edge/auth layer.
_RATE_LIMIT = int(os.environ.get("INVESTIGATE_RATE_LIMIT", "10"))       # requests per window
_RATE_WINDOW = int(os.environ.get("INVESTIGATE_RATE_WINDOW", "3600"))   # seconds
_rate_lock = threading.Lock()
_rate_hits: dict[str, list[float]] = {}


def _check_rate_limit(request: Request) -> None:
    forwarded = request.headers.get("x-forwarded-for", "")
    ip = forwarded.split(",")[0].strip() if forwarded else (
        request.client.host if request.client else "unknown"
    )
    now = time.time()
    with _rate_lock:
        if len(_rate_hits) > 10_000:  # bound memory under IP churn
            _rate_hits.clear()
        hits = [t for t in _rate_hits.get(ip, []) if now - t < _RATE_WINDOW]
        if len(hits) >= _RATE_LIMIT:
            raise HTTPException(status_code=429, detail="Rate limit exceeded — try again later")
        hits.append(now)
        _rate_hits[ip] = hits


class InvestigateRequest(BaseModel):
    company: str = Field(min_length=1, max_length=200)
    category: str = Field(max_length=100)
    country: str = Field(default="DE", pattern=r"^[A-Za-z]{2}$")  # ISO 3166-1 alpha-2
    mode: str = Field(default="full", pattern=r"^(full|recheck)$")

    @field_validator("company", "category")
    @classmethod
    def _clean_text(cls, v: str) -> str:
        v = v.strip()
        if any(ord(c) < 32 or ord(c) == 127 for c in v):
            raise ValueError("control characters are not allowed")
        return v

    @field_validator("company")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("company must not be blank")
        return v


@public_router.get("/health")
def health():
    return {"status": "ok", "agent": "hades", "version": "0.1.0"}


@router.post("/investigate")
def investigate(req: InvestigateRequest, request: Request):
    _check_rate_limit(request)
    initial_state = {
        "company_name": req.company,
        "category": req.category,
        "country": req.country,
        "is_recheck": req.mode == "recheck",
        "hermes_intel": {},
        "hermes_tracked": False,
        "skip_news": False,
        "web_results": [],
        "news_results": [],
        "sanctions_result": {},
        "registry_result": {},
        "lksg_signals": [],
        "esg_signals": [],
        "risk_scores": {},
        "report": {},
        "hermes_registered": False,
    }

    try:
        final_state = dd_graph.invoke(initial_state)
    except Exception:
        logger.exception("Investigation failed for company=%r", req.company)
        raise HTTPException(status_code=500, detail="Internal error — investigation failed")

    return {
        "company": req.company,
        "report": final_state.get("report", {}),
        "risk_scores": final_state.get("risk_scores", {}),
        "hermes_registered": final_state.get("hermes_registered", False),
    }


@router.get("/audit/{company}")
def get_audit(company: str = Path(min_length=1, max_length=200)):
    """
    Return the full investigation audit trail for a supplier, newest first.
    Up to 50 records are kept per supplier.
    """
    try:
        history = _get_hermes().get_audit(company)
    except Exception:
        logger.exception("Audit lookup failed for company=%r", company)
        raise HTTPException(status_code=500, detail="Internal error — audit lookup failed")
    return {
        "company": company,
        "investigation_count": len(history),
        "history": history,
    }


@router.get("/audit/{company}/latest")
def get_audit_latest(company: str = Path(min_length=1, max_length=200)):
    """Return only the most recent audit record for a supplier."""
    try:
        history = _get_hermes().get_audit(company)
    except Exception:
        logger.exception("Audit lookup failed for company=%r", company)
        raise HTTPException(status_code=500, detail="Internal error — audit lookup failed")
    if not history:
        raise HTTPException(status_code=404, detail=f"No audit records found for '{company}'")
    return history[0]


_CSV_FIELDS = [
    "company", "investigated_at", "mode", "category", "country",
    "overall_risk_score", "risk_level", "recommendation",
    "sanctions_hit", "sanctions_manual_review",
    "lksg_signal", "lksg_flagged_count", "esg_rating",
    "company_status", "hrb",
    "dim_sanctions", "dim_registry", "dim_news_sentiment",
    "dim_lksg_csddd", "dim_esg_labour", "dim_hermes_intelligence",
    "hermes_tracked", "hermes_registered",
    "required_next_steps",
]


def _csv_safe(value):
    """Neutralise spreadsheet formula injection (=, +, -, @, tab, CR prefixes)."""
    if isinstance(value, str) and value and value[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def _records_to_csv(records: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_CSV_FIELDS, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for r in records:
        dims = r.get("dimension_scores", {})
        steps = r.get("required_next_steps", [])
        row = {
            "company": r.get("company", ""),
            "investigated_at": r.get("investigated_at", ""),
            "mode": r.get("mode", ""),
            "category": r.get("category", ""),
            "country": r.get("country", ""),
            "overall_risk_score": r.get("overall_risk_score", ""),
            "risk_level": r.get("risk_level", ""),
            "recommendation": r.get("recommendation", ""),
            "sanctions_hit": r.get("sanctions_hit", ""),
            "sanctions_manual_review": r.get("sanctions_manual_review", ""),
            "lksg_signal": r.get("lksg_signal", ""),
            "lksg_flagged_count": r.get("lksg_flagged_count", ""),
            "esg_rating": r.get("esg_rating", ""),
            "company_status": r.get("company_status", ""),
            "hrb": r.get("hrb", ""),
            "dim_sanctions": dims.get("sanctions", ""),
            "dim_registry": dims.get("registry", ""),
            "dim_news_sentiment": dims.get("news_sentiment", ""),
            "dim_lksg_csddd": dims.get("lksg_csddd", ""),
            "dim_esg_labour": dims.get("esg_labour", ""),
            "dim_hermes_intelligence": dims.get("hermes_intelligence", ""),
            "hermes_tracked": r.get("hermes_tracked", ""),
            "hermes_registered": r.get("hermes_registered", ""),
            "required_next_steps": " | ".join(steps) if steps else "",
        }
        writer.writerow({k: _csv_safe(v) for k, v in row.items()})
    return buf.getvalue()


@router.get("/audit/export/csv")
def export_all_csv():
    """Export full audit history for ALL suppliers as a CSV file."""
    hermes = _get_hermes()
    try:
        slugs = hermes.get_all_audit_slugs()
    except Exception:
        logger.exception("CSV export failed listing audit slugs")
        raise HTTPException(status_code=500, detail="Internal error — export failed")
    all_records = []
    for slug in slugs:
        try:
            all_records.extend(hermes.get_audit(slug))
        except Exception:
            pass
    all_records.sort(key=lambda r: r.get("investigated_at", ""), reverse=True)
    csv_content = _records_to_csv(all_records)
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=hades_supplier_audit.csv"},
    )


@router.get("/audit/{company}/export/csv")
def export_company_csv(company: str = Path(min_length=1, max_length=200)):
    """Export audit history for a single supplier as a CSV file."""
    try:
        history = _get_hermes().get_audit(company)
    except Exception:
        logger.exception("CSV export failed for company=%r", company)
        raise HTTPException(status_code=500, detail="Internal error — export failed")
    if not history:
        raise HTTPException(status_code=404, detail=f"No audit records found for '{company}'")
    csv_content = _records_to_csv(history)
    # Whitelist filename chars — user input must not reach the Content-Disposition header raw
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", company)[:80] or "supplier"
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=hades_audit_{safe_name}.csv"},
    )
