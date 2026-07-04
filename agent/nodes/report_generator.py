import json
import os
from datetime import datetime
import anthropic
from agent.state import DDState
from agent.prompts import REPORT_PROMPT
from agent.nodes._utils import parse_json_response


def _summarise(data: dict | list, max_chars: int = 1500) -> str:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    return text[:max_chars] + ("..." if len(text) > max_chars else "")


def report_generator(state: DDState) -> dict:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    report_date = datetime.utcnow().strftime("%Y-%m-%d")

    prompt = REPORT_PROMPT.format(
        company_name=state["company_name"],
        category=state.get("category", ""),
        country=state.get("country", ""),
        report_date=report_date,
        risk_scores=_summarise(state.get("risk_scores", {})),
        registry=_summarise(state.get("registry_result", {})),
        sanctions=_summarise(state.get("sanctions_result", {})),
        news=_summarise(state.get("news_results", {})),
        lksg=_summarise(state.get("lksg_signals", {})),
        esg=_summarise(state.get("esg_signals", {})),
        hermes=_summarise(state.get("hermes_intel", {})),
    )

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = (message.content[0].text or "").strip()

    # The deterministic verdict computed in synthesis is the source of truth. The report
    # LLM writes the prose (executive summary, findings, next steps) but must NEVER own the
    # number — so we overwrite the three decision fields with the code-decided values after
    # parsing. A hallucinated score in the report text can't reach the user.
    decided = state.get("risk_scores", {}) or {}
    grounding = {
        k: decided[k]
        for k in ("overall_risk_score", "risk_level", "recommendation")
        if k in decided
    }

    try:
        report = parse_json_response(raw)
    except ValueError as e:
        return {
            "report": {
                "error": str(e),
                "report_date": report_date,
                "company": state["company_name"],
                "overall_risk_score": decided.get("overall_risk_score"),
                "risk_level": decided.get("risk_level", "Unknown"),
                "recommendation": decided.get("recommendation", "Manual Review Required"),
                "executive_summary": "Report generation failed — verdict is the deterministic score; review the raw research manually.",
                "required_next_steps": ["Review raw research data manually"],
            }
        }

    # Ground the money-relevant fields on code, not the model's echo of them.
    report.update(grounding)
    return {"report": report}
