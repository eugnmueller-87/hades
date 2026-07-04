import json
import os
import anthropic
from agent.state import DDState
from agent.prompts import SYNTHESIS_PROMPT
from agent.nodes._utils import parse_json_response
from agent.scoring import decide


def _summarise(data: dict | list, max_chars: int = 1500) -> str:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    return text[:max_chars] + ("..." if len(text) > max_chars else "")


def _hard_signals(state: DDState) -> dict:
    """Pull the deterministic facts the research nodes computed (NOT model prose) so the
    override rules act on evidence, not on the LLM's opinion."""
    sanctions = state.get("sanctions_result", {}) or {}
    registry = state.get("registry_result", {}) or {}
    lksg = state.get("lksg_signals", {}) or {}
    return {
        "is_sanctioned": bool(sanctions.get("is_sanctioned")),
        "priority_hit": bool(sanctions.get("priority_hit")),
        "company_status": registry.get("company_status"),
        "compliance_signal": lksg.get("compliance_signal"),
    }


def synthesis(state: DDState) -> dict:
    """The LLM ADVISES (scores each of the 6 dimensions from fuzzy research text); tested
    deterministic code DECIDES (weighted score, band, recommendation, overrides). The model
    never owns the number or the verdict — that is `agent.scoring.decide`."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    prompt = SYNTHESIS_PROMPT.format(
        company_name=state["company_name"],
        category=state.get("category", ""),
        country=state.get("country", ""),
        sanctions=_summarise(state.get("sanctions_result", {})),
        registry=_summarise(state.get("registry_result", {})),
        web=_summarise(state.get("web_results", {})),
        news=_summarise(state.get("news_results", {})),
        lksg=_summarise(state.get("lksg_signals", {})),
        esg=_summarise(state.get("esg_signals", {})),
        hermes=_summarise(state.get("hermes_intel", {})),
    )

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = (message.content[0].text or "").strip()
    signals = _hard_signals(state)

    try:
        advised = parse_json_response(raw)
    except ValueError as e:
        # Even on a model failure, the DECISION is deterministic: score every dimension
        # neutral (5.0) and let the code + hard signals decide. A parse error must never
        # produce a hallucinated verdict — the override rules still fire on real signals.
        scores = {}
        verdict = decide(scores, signals)
        return {
            "risk_scores": {
                "error": str(e),
                "scores": scores,
                "top_risk_factors": ["Synthesis LLM failed — scored neutral; verdict is deterministic"],
                "positive_signals": [],
                **verdict,
            }
        }

    # The model advised per-dimension scores; the code decides everything downstream.
    # We IGNORE any overall_risk_score / risk_level / recommendation the model emitted —
    # those are recomputed here so a hallucinated number can never reach the report.
    scores = advised.get("scores", {})
    verdict = decide(scores, signals)

    risk_scores = {
        "scores": scores,
        "top_risk_factors": advised.get("top_risk_factors", []),
        "positive_signals": advised.get("positive_signals", []),
        **verdict,  # overall_risk_score, risk_level, recommendation, override_reasons, _decided_by
    }
    return {"risk_scores": risk_scores}
