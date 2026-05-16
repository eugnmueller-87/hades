from fastapi import APIRouter
from pydantic import BaseModel

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
    # TODO: invoke LangGraph agent
    return {"status": "not_implemented", "company": req.company}
