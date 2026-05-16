import json
import os
from datetime import datetime
import anthropic
from agent.state import DDState
from agent.prompts import REPORT_PROMPT


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

    raw = message.content[0].text.strip()

    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    report = json.loads(raw)
    return {"report": report}
