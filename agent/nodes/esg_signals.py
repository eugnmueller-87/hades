from agent.state import DDState
from integrations.serper_client import serper_search as _serper

ESG_NEGATIVE_KEYWORDS = [
    # Environmental
    "environmental fine", "pollution", "Umweltverstoss", "Umweltstrafe",
    "CO2 violation", "emissions scandal", "waste dumping", "Umweltverschmutzung",
    # Labour / social
    "ILO violation", "labour rights", "union busting", "Arbeitsrechtsverletzung",
    "Gewerkschaft unterdrückt", "unsafe working conditions", "Arbeitssicherheit",
    # Governance
    "Transparency International", "corruption index", "Korruptionsindex",
    "bribery", "Bestechung", "money laundering", "Geldwäsche",
    # Forced/child labour (overlap with LkSG but ESG-framed)
    "EcoVadis low score", "ESG risk", "CSR failure",
]

ESG_POSITIVE_KEYWORDS = [
    "EcoVadis gold", "EcoVadis platinum", "ISO 14001", "ISO 45001",
    "CDP A", "sustainability award", "carbon neutral", "Nachhaltigkeitsbericht",
    "B Corp", "Ecovadis", "science based targets",
]


def _classify(text: str) -> str:
    text_lower = text.lower()
    if any(kw.lower() in text_lower for kw in ESG_NEGATIVE_KEYWORDS):
        return "negative"
    if any(kw.lower() in text_lower for kw in ESG_POSITIVE_KEYWORDS):
        return "positive"
    return "neutral"


def esg_signals(state: DDState) -> dict:
    company = state["company_name"]

    queries = [
        (f'"{company}" EcoVadis ESG score sustainability rating', "ecovadis"),
        (f'"{company}" environmental violation fine pollution', "environmental"),
        (f'"{company}" ILO labour rights Arbeitsrecht Gewerkschaft', "labour"),
        (f'"{company}" Transparency International corruption Bestechung', "governance"),
        (f'"{company}" Nachhaltigkeitsbericht CSR sustainability report', "csr"),
    ]

    results = []
    negative_results = []
    positive_results = []
    errors = []

    for query, label in queries:
        try:
            raw = _serper(query, num=4)
            for r in raw:
                combined = r.get("title", "") + " " + r.get("snippet", "")
                signal = _classify(combined)
                item = {
                    "query_label": label,
                    "title": r.get("title", ""),
                    "url": r.get("link", ""),
                    "snippet": r.get("snippet", "")[:300],
                    "date": r.get("date", ""),
                    "signal": signal,
                }
                results.append(item)
                if signal == "negative":
                    negative_results.append(item)
                elif signal == "positive":
                    positive_results.append(item)
        except Exception as e:
            errors.append(f"{label}: {str(e)}")

    neg = len(negative_results)
    pos = len(positive_results)

    if neg >= 3:
        esg_rating = "high_risk"
    elif neg >= 1:
        esg_rating = "medium_risk"
    elif pos >= 2:
        esg_rating = "positive"
    else:
        esg_rating = "neutral"

    return {
        "esg_signals": {
            "company": company,
            "esg_rating": esg_rating,  # high_risk | medium_risk | neutral | positive
            "negative_count": neg,
            "positive_count": pos,
            "negative_results": negative_results,
            "positive_results": positive_results,
            "all_results": results,
            "errors": errors,
        }
    }
