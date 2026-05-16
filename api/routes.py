from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from agent.graph import dd_graph

router = APIRouter()


class InvestigateRequest(BaseModel):
    company: str
    category: str
    country: str = "DE"
    mode: str = "full"  # "full" | "recheck"


@router.get("/health")
def health():
    return {"status": "ok", "agent": "supplier-dd-agent", "version": "0.1.0"}


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
