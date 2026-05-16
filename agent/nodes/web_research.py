import os
import httpx
from agent.state import DDState

SERPER_URL = "https://google.serper.dev/search"

NEGATIVE_KEYWORDS = [
    "fraud", "scandal", "lawsuit", "fined", "penalty", "bribery", "corruption",
    "bankrupt", "insolvency", "breach", "violation", "recall", "investigation",
    "Betrug", "Klage", "Bußgeld", "Strafe", "Bestechung", "Korruption",
    "Insolvenz", "Verstoß", "Ermittlung", "Rückruf", "Pflichtverletzung",
]


def _serper_search(query: str, gl: str = "de", hl: str = "de", num: int = 5) -> list[dict]:
    headers = {"X-API-KEY": os.environ["SERPER_API_KEY"], "Content-Type": "application/json"}
    r = httpx.post(SERPER_URL, headers=headers, json={"q": query, "gl": gl, "hl": hl, "num": num}, timeout=10)
    r.raise_for_status()
    return r.json().get("organic", [])


def _flag_negative(text: str) -> bool:
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in NEGATIVE_KEYWORDS)


def _format_result(r: dict, query_label: str) -> dict:
    snippet = r.get("snippet", "")
    return {
        "query_label": query_label,
        "title": r.get("title", ""),
        "url": r.get("link", ""),
        "snippet": snippet,
        "date": r.get("date", ""),
        "negative_flag": _flag_negative(r.get("title", "") + " " + snippet),
    }


def web_research(state: DDState) -> dict:
    company = state["company_name"]
    category = state.get("category", "")
    hermes_tracked = state.get("hermes_tracked", False)

    # Reduce depth if Hermes already has good coverage
    num_results = 3 if hermes_tracked else 5

    queries = [
        (f'"{company}" supplier review procurement', "en_general"),
        (f'"{company}" {category} supplier', "en_category"),
        (f'"{company}" Lieferant Lieferkette Bewertung', "de_general"),
        (f'"{company}" news risk warning', "en_risk"),
    ]

    results = []
    negative_count = 0
    errors = []

    for query, label in queries:
        try:
            raw = _serper_search(query, num=num_results)
            for r in raw:
                formatted = _format_result(r, label)
                results.append(formatted)
                if formatted["negative_flag"]:
                    negative_count += 1
        except Exception as e:
            errors.append(f"{label}: {str(e)}")

    return {
        "web_results": {
            "company": company,
            "total_results": len(results),
            "negative_count": negative_count,
            "has_negative_signals": negative_count > 0,
            "results": results,
            "errors": errors,
        }
    }
