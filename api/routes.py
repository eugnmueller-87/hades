import csv
import io
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from agent.graph import dd_graph
from integrations.hermes_client import HermesClient

router = APIRouter()

_hermes: HermesClient | None = None


def _get_hermes() -> HermesClient:
    global _hermes
    if _hermes is None:
        _hermes = HermesClient()
    return _hermes


class InvestigateRequest(BaseModel):
    company: str
    category: str
    country: str = "DE"
    mode: str = "full"  # "full" | "recheck"


@router.get("/health")
def health():
    return {"status": "ok", "agent": "hades", "version": "0.1.0"}


@router.post("/investigate")
def investigate(req: InvestigateRequest):
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "company": req.company,
        "report": final_state.get("report", {}),
        "risk_scores": final_state.get("risk_scores", {}),
        "hermes_registered": final_state.get("hermes_registered", False),
    }


@router.get("/audit/{company}")
def get_audit(company: str):
    """
    Return the full investigation audit trail for a supplier, newest first.
    Up to 50 records are kept per supplier.
    """
    try:
        history = _get_hermes().get_audit(company)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {
        "company": company,
        "investigation_count": len(history),
        "history": history,
    }


@router.get("/audit/{company}/latest")
def get_audit_latest(company: str):
    """Return only the most recent audit record for a supplier."""
    try:
        history = _get_hermes().get_audit(company)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
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
        writer.writerow(row)
    return buf.getvalue()


@router.get("/audit/export/csv")
def export_all_csv():
    """Export full audit history for ALL suppliers as a CSV file."""
    hermes = _get_hermes()
    try:
        slugs = hermes.get_all_audit_slugs()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
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
def export_company_csv(company: str):
    """Export audit history for a single supplier as a CSV file."""
    try:
        history = _get_hermes().get_audit(company)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not history:
        raise HTTPException(status_code=404, detail=f"No audit records found for '{company}'")
    csv_content = _records_to_csv(history)
    safe_name = company.replace(" ", "_").replace("/", "_")
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=hades_audit_{safe_name}.csv"},
    )
