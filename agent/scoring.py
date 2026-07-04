"""Deterministic risk scoring — the DECIDER, deliberately NOT an LLM.

The thesis: the LLM *advises* (it scores each of the 6 research dimensions 1-10, which is
fuzzy-text judgment a rule tree can't do), but tested deterministic code *decides* — it
computes the weighted overall score, maps it to a risk band, derives the recommendation,
and applies the hard override rules. A model that can hallucinate must be structurally
forbidden from doing the arithmetic and threshold-application that a CFO-defensible verdict
depends on.

Everything here is pure, side-effect-free, and unit-tested. No network, no LLM, no clock.
"""
from __future__ import annotations

# The six dimensions and their fixed weights (sum = 1.00). Order is stable for reporting.
WEIGHTS = {
    "sanctions": 0.25,
    "registry": 0.15,
    "news_sentiment": 0.15,
    "lksg_csddd": 0.20,
    "esg_labour": 0.15,
    "hermes_intelligence": 0.10,
}

# Risk-band thresholds — a score S maps to exactly one band. Half-open bands so there is
# no ambiguity at a boundary (e.g. 6.5 is High, 8.0 is Critical).
#   Low:      1.0 <= S < 4.0
#   Medium:   4.0 <= S < 6.5
#   High:     6.5 <= S < 8.0
#   Critical: 8.0 <= S <= 10.0
_BANDS = [
    (8.0, "Critical"),
    (6.5, "High"),
    (4.0, "Medium"),
    (0.0, "Low"),
]

# Band → base recommendation. Overrides below can only make this MORE conservative.
_BAND_RECOMMENDATION = {
    "Low": "Approve",
    "Medium": "Conditional Approval",
    "High": "Conditional Approval",
    "Critical": "Block",
}

# Recommendation severity order, so an override never softens a verdict.
_REC_SEVERITY = {"Approve": 0, "Conditional Approval": 1, "Block": 2}


def _clamp_score(v) -> float:
    """Coerce a model-provided dimension score to a float in [1, 10]. Never trust the range."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        # A missing/garbage dimension score fails SAFE toward risk, not toward approval.
        return 5.0
    return max(1.0, min(10.0, f))


def weighted_overall(scores: dict) -> float:
    """Deterministic weighted average of the six dimension scores, rounded to 1 decimal.
    Missing dimensions are clamped to a neutral 5.0 (fail-safe, never dropped)."""
    total = 0.0
    for dim, w in WEIGHTS.items():
        raw = scores.get(dim)
        s = _clamp_score(raw.get("score") if isinstance(raw, dict) else raw)
        total += s * w
    return round(total, 1)


def band_for(overall: float) -> str:
    for threshold, name in _BANDS:
        if overall >= threshold:
            return name
    return "Low"


def _escalate(current: str, target: str) -> str:
    """Return the MORE severe of two recommendations. Overrides can only tighten."""
    return target if _REC_SEVERITY[target] > _REC_SEVERITY[current] else current


def apply_overrides(recommendation: str, scores: dict, signals: dict) -> tuple[str, list[str]]:
    """Hard override rules that can only make the verdict more conservative, never softer.
    `signals` carries the deterministic facts from the research nodes (not model prose).
    Returns (final_recommendation, list_of_triggered_override_reasons)."""
    rec = recommendation
    reasons: list[str] = []

    # 1. A priority sanctions hit is an automatic Block — non-negotiable.
    if signals.get("is_sanctioned") and signals.get("priority_hit"):
        rec = _escalate(rec, "Block")
        reasons.append("Sanctions: confirmed priority watchlist hit → Block")

    # 2. A dissolved/insolvent registry status can never be a clean Approve.
    status = (signals.get("company_status") or "").lower()
    if status in {"dissolved", "insolvent", "dissolved/insolvent"}:
        rec = _escalate(rec, "Conditional Approval")
        reasons.append(f"Registry: company status '{status}' → at least Conditional")

    # 3. An LkSG/CSDDD red flag can never be a clean Approve.
    if (signals.get("compliance_signal") or "").lower() == "red_flag":
        rec = _escalate(rec, "Conditional Approval")
        reasons.append("LkSG/CSDDD: red flag → at least Conditional")

    # 4. A very high sanctions dimension score (>=9) forces at least Conditional even
    #    without a confirmed priority hit (defense in depth if the flags disagree).
    sanc = scores.get("sanctions")
    sanc_score = _clamp_score(sanc.get("score") if isinstance(sanc, dict) else sanc)
    if sanc_score >= 9.0:
        rec = _escalate(rec, "Conditional Approval")
        reasons.append("Sanctions dimension score >= 9 → at least Conditional")

    return rec, reasons


def decide(scores: dict, signals: dict | None = None) -> dict:
    """The single deterministic entry point. Takes the LLM's per-dimension scores + the
    research nodes' hard signals, returns the computed verdict. No LLM, no arithmetic by
    the model — this function alone owns the number, the band, and the recommendation."""
    signals = signals or {}
    overall = weighted_overall(scores)
    band = band_for(overall)
    base_rec = _BAND_RECOMMENDATION[band]
    rec, override_reasons = apply_overrides(base_rec, scores, signals)
    return {
        "overall_risk_score": overall,
        "risk_level": band,
        "recommendation": rec,
        "override_reasons": override_reasons,
        "_decided_by": "deterministic",  # provenance marker — never the LLM
    }
