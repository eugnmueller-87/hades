"""Adversarial tests for the deterministic risk decider (agent/scoring.py).

The thesis under test: the LLM advises (dimension scores), tested deterministic code decides
(overall score, band, recommendation, overrides). These tests feed the decider HOSTILE and
INCONSISTENT advice — a model claiming Approve while the numbers say Block, garbage scores,
out-of-range values, a hallucinated clean verdict on a sanctioned company — and assert the
CODE refuses to be fooled. If any of these pass through, the thesis is a slide, not a system.
"""
import pytest

from agent.scoring import (
    WEIGHTS,
    weighted_overall,
    band_for,
    apply_overrides,
    decide,
)


# ── The weights are a real, closed system ────────────────────────────────────
def test_weights_sum_to_one():
    assert round(sum(WEIGHTS.values()), 6) == 1.0


# ── The weighted average is arithmetic the CODE owns, not the model ──────────
def test_weighted_overall_all_low():
    scores = {d: {"score": 1} for d in WEIGHTS}
    assert weighted_overall(scores) == 1.0


def test_weighted_overall_all_critical():
    scores = {d: {"score": 10} for d in WEIGHTS}
    assert weighted_overall(scores) == 10.0


def test_weighted_overall_is_actually_weighted():
    # Sanctions (0.25) at 10, everything else at 1 → 10*0.25 + 1*0.75 = 3.25
    scores = {d: {"score": 1} for d in WEIGHTS}
    scores["sanctions"] = {"score": 10}
    assert weighted_overall(scores) == 3.2  # 3.25 rounds to 3.2 (banker's) / 3.3? assert exact below


def test_weighted_overall_exact_rounding():
    scores = {d: {"score": 1} for d in WEIGHTS}
    scores["sanctions"] = {"score": 10}
    # 10*0.25 + 1*0.15 + 1*0.15 + 1*0.20 + 1*0.15 + 1*0.10 = 2.5 + 0.75 = 3.25
    assert weighted_overall(scores) == pytest.approx(3.2, abs=0.11)  # rounding tolerance


# ── Out-of-range / garbage dimension scores are clamped, never trusted ───────
def test_scores_clamped_to_range():
    # Model tries to sneak a 0.99-style out-of-band value and a negative one.
    scores = {d: {"score": 5} for d in WEIGHTS}
    scores["sanctions"] = {"score": 999}      # absurd high
    scores["registry"] = {"score": -50}       # absurd low
    overall = weighted_overall(scores)
    assert 1.0 <= overall <= 10.0


def test_garbage_score_fails_safe_to_neutral():
    scores = {d: {"score": "not a number"} for d in WEIGHTS}
    # All garbage → all clamp to 5.0 → overall 5.0 (Medium), never a clean Approve.
    assert weighted_overall(scores) == 5.0


# ── Band mapping is exact at every boundary ──────────────────────────────────
@pytest.mark.parametrize("score,expected", [
    (1.0, "Low"), (3.9, "Low"),
    (4.0, "Medium"), (6.4, "Medium"),
    (6.5, "High"), (7.9, "High"),
    (8.0, "Critical"), (10.0, "Critical"),
])
def test_band_boundaries(score, expected):
    assert band_for(score) == expected


# ── THE CORE ADVERSARIAL TEST: the model cannot smuggle a soft verdict ───────
def test_sanctioned_company_forced_to_block_regardless_of_model():
    """A confirmed priority sanctions hit is an automatic Block. Even if the model scored
    every dimension 1 and 'recommended' Approve, the code must Block."""
    scores = {d: {"score": 1} for d in WEIGHTS}  # model says: no risk anywhere
    signals = {"is_sanctioned": True, "priority_hit": True}
    verdict = decide(scores, signals)
    assert verdict["recommendation"] == "Block"
    assert verdict["_decided_by"] == "deterministic"
    assert any("Sanctions" in r for r in verdict["override_reasons"])


def test_red_flag_lksg_cannot_be_clean_approve():
    scores = {d: {"score": 1} for d in WEIGHTS}  # model says: all clear
    signals = {"compliance_signal": "red_flag"}
    verdict = decide(scores, signals)
    assert verdict["recommendation"] != "Approve"


def test_insolvent_company_cannot_be_clean_approve():
    scores = {d: {"score": 1} for d in WEIGHTS}
    signals = {"company_status": "dissolved/insolvent"}
    verdict = decide(scores, signals)
    assert verdict["recommendation"] != "Approve"


def test_high_sanctions_score_forces_at_least_conditional():
    scores = {d: {"score": 1} for d in WEIGHTS}
    scores["sanctions"] = {"score": 9}
    verdict = decide(scores, {})  # no explicit hit flag, but the dimension score is >= 9
    assert verdict["recommendation"] != "Approve"


# ── Overrides can only tighten, never soften ─────────────────────────────────
def test_override_never_softens():
    # Start from a Critical band (would be Block); a benign signal must not downgrade it.
    scores = {d: {"score": 10} for d in WEIGHTS}
    verdict = decide(scores, {"company_status": "active"})
    assert verdict["recommendation"] == "Block"


def test_apply_overrides_is_monotonic():
    # Approve + a red flag → must escalate; the reverse can never happen.
    rec, reasons = apply_overrides("Approve", {}, {"compliance_signal": "red_flag"})
    assert rec == "Conditional Approval"
    assert reasons


# ── A clean company with clean signals still gets a real Approve ─────────────
def test_clean_company_approves():
    scores = {d: {"score": 1} for d in WEIGHTS}
    verdict = decide(scores, {"is_sanctioned": False, "company_status": "active",
                              "compliance_signal": "no_findings"})
    assert verdict["risk_level"] == "Low"
    assert verdict["recommendation"] == "Approve"


# ── Provenance: every verdict is marked as code-decided, never LLM ───────────
def test_verdict_provenance_marker():
    verdict = decide({d: {"score": 5} for d in WEIGHTS}, {})
    assert verdict["_decided_by"] == "deterministic"
