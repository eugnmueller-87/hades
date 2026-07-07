"""Tests for the risky external-parsing nodes (registry regex + LkSG classifier).

These are the highest-risk pure paths in Hades: they turn noisy web-search snippets into
compliance signals. Previously this file was a 2-line stub. These tests pin the parsing and,
critically, the LkSG false-positive fix (the classifier used to flag a company's OWN compliance
page as a red flag because the page echoed the search terms).
"""
from agent.nodes.registry_lookup import _extract_hrb, _extract_amtsgericht
from agent.nodes.lksg_signals import _flag_result


# ── Registry regex extraction ────────────────────────────────────────────────
def test_extract_hrb_basic():
    assert _extract_hrb("Eingetragen im Handelsregister HRB 12345 Berlin") == "HRB12345"


def test_extract_hrb_no_space():
    assert _extract_hrb("HRB98765") == "HRB98765"


def test_extract_hrb_absent():
    assert _extract_hrb("no registry number here") is None


def test_extract_amtsgericht():
    assert _extract_amtsgericht("Amtsgericht Charlottenburg") == "Amtsgericht Charlottenburg"


def test_extract_amtsgericht_absent():
    assert _extract_amtsgericht("nothing relevant") is None


# ── LkSG classifier: the echo / false-positive fix ───────────────────────────
def test_lksg_does_not_flag_query_echo():
    # A result that only echoes the SEARCH TERMS (BAFA, LkSG, human rights) is NOT a finding.
    r = {"title": "ACME AG — BAFA & LkSG compliance",
         "snippet": "ACME AG supports the Lieferkettengesetz and human rights due diligence."}
    assert _flag_result(r) is False


def test_lksg_does_not_flag_positive_policy():
    r = {"title": "ACME committed to preventing forced labour",
         "snippet": "Zero tolerance policy; committed to preventing forced labour in our supply chain."}
    assert _flag_result(r) is False


def test_lksg_flags_real_adverse_finding():
    # An actual fine / conviction IS a finding.
    r = {"title": "ACME AG mit Bußgeld belegt",
         "snippet": "Das Unternehmen wurde wegen Zwangsarbeit verurteilt und mit einem Bußgeld belegt."}
    assert _flag_result(r) is True


def test_lksg_flags_english_violation():
    r = {"title": "Supplier fined for human rights violation",
         "snippet": "The company was fined after a proven human rights violation at its plant."}
    assert _flag_result(r) is True


def test_lksg_negation_suppresses_flag():
    r = {"title": "Audit: no violation found",
         "snippet": "Independent audit found no violation of forced labour standards."}
    assert _flag_result(r) is False
