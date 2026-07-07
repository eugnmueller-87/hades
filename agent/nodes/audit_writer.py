from datetime import datetime, timezone

from agent.state import DDState
from integrations.hermes_client import HermesClient

_client = None


def _get_client() -> HermesClient:
    global _client
    if _client is None:
        _client = HermesClient()
    return _client


def audit_writer(state: DDState) -> dict:
    """
    Write a structured audit record to Redis after every investigation.
    Key: hades:audit:<slug>  (list, newest first, capped at 50 entries)
    """
    report = state.get("report", {})
    risk_scores = state.get("risk_scores", {})
    scores = risk_scores.get("scores", {})
    # The audit trail is a compliance record — it must reflect the DETERMINISTIC facts the
    # code decided, NOT the LLM's echo of them in `report`. `risk_scores` is the output of
    # `scoring.decide`; `sanctions_result`/`lksg_signals` are the research nodes' computed
    # facts. We read those first and fall back to `report` only for narrative-only fields.
    sanctions = state.get("sanctions_result", {}) or {}
    lksg = state.get("lksg_signals", {}) or {}
    registry = state.get("registry_result", {}) or {}

    entry = {
        "investigated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "recheck" if state.get("is_recheck") else "full",
        "company": state["company_name"],
        "category": state.get("category", ""),
        "country": state.get("country", ""),
        # Top-level verdict — the DETERMINISTIC decision, not the model's restatement.
        "overall_risk_score": risk_scores.get("overall_risk_score"),
        "risk_level": risk_scores.get("risk_level"),
        "recommendation": risk_scores.get("recommendation"),
        "override_reasons": risk_scores.get("override_reasons", []),
        "decided_by": risk_scores.get("_decided_by", "deterministic"),
        # Per-dimension scores
        "dimension_scores": {
            dim: (val.get("score") if isinstance(val, dict) else val) for dim, val in scores.items()
        },
        # Key compliance flags — from the deterministic sanctions/lksg facts, not report prose.
        "sanctions_hit": bool(sanctions.get("is_sanctioned", False)),
        "sanctions_manual_review": bool(sanctions.get("manual_review_required", False)),
        "sanctions_status": sanctions.get("status"),
        "sanctions_sources_unavailable": sanctions.get("sources_unavailable", []),
        "lksg_signal": lksg.get("compliance_signal") or report.get("lksg_csddd_assessment", {}).get("compliance_signal"),
        "lksg_flagged_count": lksg.get("flagged_count") or report.get("lksg_csddd_assessment", {}).get("flagged_count"),
        "esg_rating": report.get("esg_labour", {}).get("esg_rating"),
        # Registry — prefer the deterministic registry result.
        "company_status": registry.get("company_status") or report.get("company_overview", {}).get("company_status"),
        "hrb": registry.get("hrb") or report.get("company_overview", {}).get("hrb"),
        # Hermes
        "hermes_tracked": state.get("hermes_tracked", False),
        "hermes_registered": state.get("hermes_registered", False),
        # Action items
        "required_next_steps": report.get("required_next_steps", []),
    }

    try:
        _get_client().write_audit(state["company_name"], entry)
    except Exception:
        pass  # audit failure must never break the investigation response

    return {}
