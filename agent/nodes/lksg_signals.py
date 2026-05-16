from agent.state import DDState
from integrations.serper_client import serper_search as _serper


# Signals that indicate actual LkSG/CSDDD compliance problems
HARD_FLAGS = [
    "BAFA", "Beschwerde", "Bußgeld", "Klage", "Menschenrechtsverletzung",
    "NCP", "complaint", "enforcement", "violation", "human rights abuse",
    "forced labour", "Zwangsarbeit", "Kinderarbeit", "child labour",
    "Germanwatch", "ECCHR", "Bread for the World", "Lieferkettengesetz",
]


def _flag_result(result: dict) -> bool:
    text = (result.get("title", "") + " " + result.get("snippet", "")).lower()
    return any(kw.lower() in text for kw in HARD_FLAGS)


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
