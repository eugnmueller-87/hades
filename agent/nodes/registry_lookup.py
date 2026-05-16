import re
from agent.state import DDState
from integrations.serper_client import serper_search as _serper


def _extract_hrb(text: str) -> str | None:
    match = re.search(r"HRB\s*\d+", text, re.IGNORECASE)
    return re.sub(r"\s+", "", match.group(0)) if match else None


def _extract_amtsgericht(text: str) -> str | None:
    match = re.search(r"Amtsgericht\s+\w+", text, re.IGNORECASE)
    return match.group(0) if match else None


def registry_lookup(state: DDState) -> dict:
    company = state["company_name"]
    country = state.get("country", "DE")

    results = []
    hrb = None
    amtsgericht = None
    legal_address = None
    company_status = "unknown"
    source_urls = []

    try:
        # Primary: NorthData — best structured DE registry data
        nd_results = _serper(f'"{company}" site:northdata.com', num=3)
        for r in nd_results:
            snippet = r.get("snippet", "")
            title = r.get("title", "")
            link = r.get("link", "")
            combined = f"{title} {snippet}"

            if not hrb:
                hrb = _extract_hrb(combined)
            if not amtsgericht:
                amtsgericht = _extract_amtsgericht(combined)

            results.append({
                "source": "NorthData",
                "title": title,
                "snippet": snippet,
                "url": link,
            })
            source_urls.append(link)

        # Secondary: Unternehmensregister — official federal gazette filings
        ur_results = _serper(f'"{company}" site:unternehmensregister.de', num=2)
        for r in ur_results:
            results.append({
                "source": "Unternehmensregister",
                "title": r.get("title", ""),
                "snippet": r.get("snippet", ""),
                "url": r.get("link", ""),
            })
            source_urls.append(r.get("link", ""))

        # Fallback web search for address + status signals
        general = _serper(f'"{company}" Impressum Handelsregister HRB Sitz', num=3)
        for r in general:
            snippet = r.get("snippet", "")
            if not hrb:
                hrb = _extract_hrb(snippet)
            if not amtsgericht:
                amtsgericht = _extract_amtsgericht(snippet)
            if not legal_address and any(kw in snippet for kw in ["GmbH", "AG", "Sitz", "Straße", "Platz"]):
                legal_address = snippet[:200]

        # Infer company status from results
        all_text = " ".join(r.get("snippet", "") + r.get("title", "") for r in results).lower()
        if any(w in all_text for w in ["insolvenz", "insolvent", "liquidation", "gelöscht", "aufgelöst", "dissolved"]):
            company_status = "dissolved/insolvent"
        elif results:
            company_status = "active"

    except Exception as e:
        return {
            "registry_result": {
                "company": company,
                "country": country,
                "status": "error",
                "error": str(e),
                "hrb": None,
                "amtsgericht": None,
                "legal_address": None,
                "company_status": "unknown",
                "sources": [],
                "raw_results": [],
            }
        }

    return {
        "registry_result": {
            "company": company,
            "country": country,
            "status": "ok",
            "hrb": hrb,
            "amtsgericht": amtsgericht,
            "legal_address": legal_address,
            "company_status": company_status,
            "sources": source_urls,
            "raw_results": results,
        }
    }
