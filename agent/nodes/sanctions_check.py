"""
Sanctions check against OFAC SDN List and UN Security Council Consolidated List.
Both are authoritative, free, public XML sources — no API key required.

OFAC SDN: US Treasury, ~28 MB, updated regularly
UN SC:    UN Security Council consolidated list, ~2 MB
EU FSF:   Blocks automated access; flagged for manual verification in every report

Both XML trees are cached in memory for 24 hours to avoid re-downloading on
every request (OFAC alone is 28 MB).
"""

import re
import time
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher
import httpx
from agent.state import DDState

OFAC_SDN_URL = "https://www.treasury.gov/ofac/downloads/sdn.xml"
UN_SC_URL = "https://scsanctions.un.org/resources/xml/en/consolidated.xml"

MATCH_THRESHOLD = 0.82
_CACHE_TTL = 86_400  # 24 hours

# Module-level cache: (ET.Element, fetched_at_epoch)
_ofac_cache: tuple[ET.Element, float] | None = None
_un_cache: tuple[ET.Element, float] | None = None


def _normalise(name: str) -> str:
    name = name.lower()
    suffixes = [
        r"\bgmbh\b", r"\bag\b", r"\binc\.?\b", r"\bllc\.?\b", r"\bltd\.?\b",
        r"\bcorp\.?\b", r"\bse\b", r"\bsrl\b", r"\bsa\b", r"\bbv\b",
        r"\bco\.?\b", r"\bplc\.?\b", r"\bgroup\b", r"\bholding[s]?\b",
        r"\btechnologies\b", r"\btech\b",
    ]
    for s in suffixes:
        name = re.sub(s, "", name)
    name = re.sub(r"[^\w\s]", " ", name)
    return " ".join(name.split())


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _normalise(a), _normalise(b)).ratio()


def _get_xml(url: str, cache_slot: str, timeout: int = 30) -> ET.Element | None:
    global _ofac_cache, _un_cache
    now = time.time()
    cache = _ofac_cache if cache_slot == "ofac" else _un_cache

    if cache is not None and (now - cache[1]) < _CACHE_TTL:
        return cache[0]

    try:
        r = httpx.get(url, timeout=timeout, follow_redirects=True)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        entry = (root, now)
        if cache_slot == "ofac":
            _ofac_cache = entry
        else:
            _un_cache = entry
        return root
    except Exception:
        # Return stale cache rather than nothing, if available
        return cache[0] if cache is not None else None


def _check_ofac(company: str) -> list[dict] | None:
    """Returns hit list, or None if the OFAC list could not be fetched."""
    root = _get_xml(OFAC_SDN_URL, "ofac")
    if root is None:
        return None

    hits = []
    for entry in root.iter():
        if not entry.tag.endswith("sdnEntry"):
            continue

        sdn_type = next(
            (c.text or "" for c in entry if c.tag.endswith("sdnType")), ""
        )
        if sdn_type == "Individual":
            continue

        names = []
        for child in entry:
            if child.tag.endswith("lastName") and child.text:
                names.append(child.text)
            if child.tag.endswith("akaList"):
                for aka in child:
                    for aka_child in aka:
                        if aka_child.tag.endswith("lastName") and aka_child.text:
                            names.append(aka_child.text)

        best_score = max((_similarity(company, n) for n in names), default=0.0)
        if best_score >= MATCH_THRESHOLD:
            programme = next(
                (
                    pc.text
                    for child in entry if child.tag.endswith("programList")
                    for prog in child
                    for pc in prog if pc.tag.endswith("program") and pc.text
                ),
                "",
            )
            hits.append({
                "source": "OFAC Specially Designated Nationals",
                "dataset": "us_ofac_sdn",
                "matched_name": names[0] if names else "",
                "score": round(best_score, 3),
                "programme": programme,
            })

    return hits


def _check_un_sc(company: str) -> list[dict] | None:
    """Returns hit list, or None if the UN list could not be fetched."""
    root = _get_xml(UN_SC_URL, "un")
    if root is None:
        return None

    hits = []
    for entity in root.iter():
        if not entity.tag.endswith("ENTITY"):
            continue

        names = []
        for child in entity:
            if child.tag.endswith("FIRST_NAME") and child.text:
                names.append(child.text)
            if child.tag.endswith("ALIAS_NAME") and child.text:
                names.append(child.text)
            if child.tag.endswith("NAME_ORIGINAL_SCRIPT") and child.text:
                names.append(child.text)

        best_score = max((_similarity(company, n) for n in names), default=0.0)
        if best_score >= MATCH_THRESHOLD:
            hits.append({
                "source": "UN Security Council Consolidated List",
                "dataset": "un_sc_sanctions",
                "matched_name": names[0] if names else "",
                "score": round(best_score, 3),
                "programme": "",
            })

    return hits


def sanctions_check(state: DDState) -> dict:
    company = state["company_name"]

    ofac_hits = _check_ofac(company)
    un_hits = _check_un_sc(company)

    # Fail closed: a list that could not be fetched must not read as "no hits"
    sources_checked = []
    sources_unavailable = []
    if ofac_hits is None:
        ofac_hits = []
        sources_unavailable.append("OFAC SDN")
    else:
        sources_checked.append("OFAC SDN")
    if un_hits is None:
        un_hits = []
        sources_unavailable.append("UN SC Consolidated List")
    else:
        sources_checked.append("UN SC Consolidated List")

    all_hits = ofac_hits + un_hits
    datasets_matched = sorted({h["dataset"] for h in all_hits})
    priority_hit = bool(all_hits)

    return {
        "sanctions_result": {
            "company": company,
            "status": "ok" if not sources_unavailable else "degraded",
            "is_sanctioned": bool(all_hits),
            "matches": all_hits,
            "datasets_matched": datasets_matched,
            "priority_hit": priority_hit,
            "manual_review_required": bool(all_hits) or bool(sources_unavailable),
            "eu_fsf_manual_required": True,
            "sources_checked": sources_checked,
            "sources_unavailable": sources_unavailable,
            "sources_note": "EU Financial Sanctions File requires manual verification at webgate.ec.europa.eu/fsd",
        }
    }
