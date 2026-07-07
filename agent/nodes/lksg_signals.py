from agent.state import DDState
from integrations.serper_client import serper_search as _serper


# Signals that indicate actual LkSG/CSDDD compliance problems
# ADVERSE-FINDING terms only — words that indicate an ACTUAL problem (a fine, a lawsuit, a
# proven violation, forced/child labour). These do NOT appear just because we searched.
# NOTE: query-echo terms (BAFA, NCP, LkSG, Lieferkettengesetz, "human rights", Germanwatch,
# ECCHR, "supply chain due diligence", "complaint") are DELIBERATELY EXCLUDED — they appear in
# results simply because they were the search query, so counting them flags a company's own
# compliance page as a red flag. That echo made this classifier a false-positive machine.
HARD_FLAGS = [
    "Bußgeld", "Geldstrafe", "Klage", "verurteilt", "convicted", "fined", "penalty",
    "Menschenrechtsverletzung", "human rights abuse", "human rights violation",
    "forced labour", "forced labor", "Zwangsarbeit", "Kinderarbeit", "child labour", "child labor",
    "Ausbeutung", "exploitation", "sanctioned", "banned", "Verstoß gegen", "found guilty",
]

# A finding is only credible if an adverse term appears NEAR a negative/enforcement context,
# not in isolation (e.g. "no violation found" or "committed to preventing forced labour" must
# NOT flag). We require an adverse term AND that the snippet is not obviously a negation/positive.
_NEGATION_CUES = [
    "no violation", "keine verstöße", "keine verletzung", "not found", "cleared",
    "committed to", "verpflichtet sich", "prevent", "prevention", "policy against",
    "zero tolerance", "compliance with", "einhaltung",
]


def _flag_result(result: dict) -> bool:
    text = (result.get("title", "") + " " + result.get("snippet", "")).lower()
    if not any(kw.lower() in text for kw in HARD_FLAGS):
        return False
    # Adverse term present — but suppress obvious negations / policy statements.
    if any(neg in text for neg in _NEGATION_CUES):
        return False
    return True


def lksg_signals(state: DDState) -> dict:
    company = state["company_name"]

    queries = [
        # BAFA enforcement — German authority for LkSG
        (f'"{company}" BAFA LkSG', "bafa"),
        # NCP complaints — OECD National Contact Point
        (f'"{company}" NCP Beschwerde OECD Menschenrechte', "ncp"),
        # NGO investigations — Germanwatch, ECCHR, Brot für die Welt
        (f'"{company}" Lieferkette Menschenrechte Germanwatch ECCHR', "ngo"),
        # Supply chain law violations in English press
        (f'"{company}" supply chain due diligence human rights violation', "en_lksg"),
        # Forced / child labour specific
        (f'"{company}" Zwangsarbeit OR Kinderarbeit OR "forced labour" OR "child labour"', "labour"),
    ]

    results = []
    flagged_results = []
    errors = []

    for query, label in queries:
        try:
            raw = _serper(query, num=5)
            for r in raw:
                item = {
                    "query_label": label,
                    "title": r.get("title", ""),
                    "url": r.get("link", ""),
                    "snippet": r.get("snippet", ""),
                    "date": r.get("date", ""),
                    "hard_flag": _flag_result(r),
                }
                results.append(item)
                if item["hard_flag"]:
                    flagged_results.append(item)
        except Exception as e:
            errors.append(f"{label}: {str(e)}")

    # Determine LkSG compliance signal
    flag_count = len(flagged_results)
    if flag_count == 0:
        compliance_signal = "no_findings"
    elif flag_count <= 2:
        compliance_signal = "needs_monitoring"
    else:
        compliance_signal = "red_flag"

    return {
        "lksg_signals": {
            "company": company,
            "total_results": len(results),
            "flagged_count": flag_count,
            "compliance_signal": compliance_signal,  # no_findings | needs_monitoring | red_flag
            "flagged_results": flagged_results,
            "all_results": results,
            "errors": errors,
        }
    }
