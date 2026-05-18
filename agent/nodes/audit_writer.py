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

    entry = {
        "investigated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "recheck" if state.get("is_recheck") else "full",
        "company": state["company_name"],
        "category": state.get("category", ""),
        "country": state.get("country", ""),
        # Top-level verdict
        "overall_risk_score": report.get("overall_risk_score") or risk_scores.get("overall_risk_score"),
        "risk_level": report.get("risk_level") or risk_scores.get("risk_level"),
        "recommendation": report.get("recommendation") or risk_scores.get("recommendation"),
        # Per-dimension scores
        "dimension_scores": {
            dim: val.get("score") for dim, val in scores.items()
        },
        # Key compliance flags
        "sanctions_hit": report.get("sanctions_status", {}).get("is_sanctioned", False),
        "sanctions_manual_review": report.get("sanctions_status", {}).get("manual_review_required", False),
        "lksg_signal": report.get("lksg_csddd_assessment", {}).get("compliance_signal"),
        "lksg_flagged_count": report.get("lksg_csddd_assessment", {}).get("flagged_count"),
        "esg_rating": report.get("esg_labour", {}).get("esg_rating"),
        # Registry
        "company_status": report.get("company_overview", {}).get("company_status"),
        "hrb": report.get("company_overview", {}).get("hrb"),
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
