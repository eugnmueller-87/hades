from fastapi import APIRouter, HTTPException
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
