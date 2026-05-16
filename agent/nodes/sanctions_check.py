import os
import httpx
from agent.state import DDState

# Matching API — query by entity (more precise than name search, fewer false positives)
OPENSANCTIONS_MATCH_URL = "https://api.opensanctions.org/match/default"
OPENSANCTIONS_SEARCH_URL = "https://api.opensanctions.org/search/default"

PRIORITY_DATASETS = {
    "us_ofac_sdn",        # US OFAC Specially Designated Nationals
    "eu_fsf",             # EU Financial Sanctions (consolidated list)
    "un_sc_sanctions",    # UN Security Council sanctions
    "gb_hmt_sanctions",   # UK HM Treasury
    "eu_eeas_sanctions",  # EU External Action Service
    "de_bafa_sanctions",  # German BAFA export control
    "interpol_red_notices",
}


def _build_headers() -> dict:
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    api_key = os.environ.get("OPENSANCTIONS_API_KEY", "")
    if api_key:
        headers["Authorization"] = f"ApiKey {api_key}"
    return headers


def _error_result(company: str, error: str) -> dict:
    """Safe default on any error — never false-clear, always require manual review."""
    return {
        "sanctions_result": {
            "company": company,
            "status": "inconclusive",
            "error": error,
            "is_sanctioned": None,
            "matches": [],
            "datasets_matched": [],
            "priority_hit": False,
            "manual_review_required": True,
        }
    }


def _parse_matches(results: list[dict], company: str) -> dict:
    # Score threshold 0.85 — high confidence matches only
    strong = [r for r in results if r.get("score", 0) >= 0.85]

    if not strong:
        return {
            "sanctions_result": {
                "company": company,
                "status": "ok",
                "is_sanctioned": False,
                "matches": [],
                "datasets_matched": [],
                "priority_hit": False,
                "manual_review_required": False,
                "total_candidates": len(results),
            }
        }

    matched_datasets = set()
    match_summaries = []
    for match in strong:
        datasets = match.get("datasets", [])
        matched_datasets.update(datasets)
        match_summaries.append({
            "name": match.get("caption", ""),
            "score": round(match.get("score", 0), 3),
            "schema": match.get("schema", ""),
            "datasets": datasets,
            "countries": match.get("properties", {}).get("country", []),
            "topics": match.get("properties", {}).get("topics", []),
            "addresses": match.get("properties", {}).get("address", [])[:2],
        })

    priority_hit = bool(matched_datasets & PRIORITY_DATASETS)

    return {
        "sanctions_result": {
            "company": company,
            "status": "ok",
            "is_sanctioned": True,
            "matches": match_summaries,
            "datasets_matched": sorted(matched_datasets),
            "priority_hit": priority_hit,
            "manual_review_required": False,
            "total_candidates": len(results),
        }
    }


def sanctions_check(state: DDState) -> dict:
    company = state["company_name"]
    country = state.get("country", "")
    headers = _build_headers()

    # Primary: matching API — query by entity structure (fewer false positives)
    try:
        body = {
            "queries": {
                "q1": {
                    "schema": "Company",
                    "properties": {
                        "name": [company],
                        **({"country": [country.lower()]} if country else {}),
                    },
                }
            }
        }
        r = httpx.post(OPENSANCTIONS_MATCH_URL, headers=headers, json=body, timeout=15)
        r.raise_for_status()
        data = r.json()
        results = data.get("responses", {}).get("q1", {}).get("results", [])
        return _parse_matches(results, company)

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 403:
            # No key or invalid key — fall back to search API
            pass
        else:
            return _error_result(company, f"Match API error {e.response.status_code}")
    except Exception as e:
        return _error_result(company, str(e))

    # Fallback: search API (requires key too, but different endpoint)
    try:
        r = httpx.get(
            OPENSANCTIONS_SEARCH_URL,
            headers=headers,
            params={"q": company, "limit": 10, "fuzzy": "false"},
            timeout=15,
        )
        r.raise_for_status()
        results = r.json().get("results", [])
        return _parse_matches(results, company)
    except Exception as e:
        return _error_result(company, f"Both match and search APIs failed: {str(e)}")
