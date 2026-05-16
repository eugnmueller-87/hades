"""
Sanctions check against OFAC SDN List and UN Security Council Consolidated List.
Both are authoritative, free, public XML sources — no API key required.

OFAC SDN: US Treasury, updated regularly — gold standard for global sanctions
UN SC:    UN Security Council consolidated list — international baseline
EU FSF:   Blocks automated access; flagged as requiring manual verification
"""

import re
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher
import httpx
from agent.state import DDState

OFAC_SDN_URL = "https://www.treasury.gov/ofac/downloads/sdn.xml"
UN_SC_URL = "https://scsanctions.un.org/resources/xml/en/consolidated.xml"

MATCH_THRESHOLD = 0.82


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


def _fetch_xml(url: str, timeout: int = 30) -> ET.Element | None:
    try:
        r = httpx.get(url, timeout=timeout, follow_redirects=True)
        r.raise_for_status()
        return ET.fromstring(r.content)
    except Exception:
        return None


def _check_ofac(company: str) -> list[dict]:
    """Match against OFAC Specially Designated Nationals list."""
    root = _fetch_xml(OFAC_SDN_URL)
    if root is None:
        return []

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


def _check_un_sc(company: str) -> list[dict]:
    """Match against UN Security Council consolidated sanctions list."""
    root = _fetch_xml(UN_SC_URL)
    if root is None:
        return []

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
    all_hits = ofac_hits + un_hits

    datasets_matched = sorted({h["dataset"] for h in all_hits})
    # Both OFAC and UN SC are priority lists — any match is a priority hit
    priority_hit = bool(all_hits)

    return {
        "sanctions_result": {
            "company": company,
            "status": "ok",
            "is_sanctioned": bool(all_hits),
            "matches": all_hits,
            "datasets_matched": datasets_matched,
            "priority_hit": priority_hit,
            "manual_review_required": bool(all_hits),
            # EU FSF requires browser session — flag for manual check
            "eu_fsf_manual_required": True,
            "sources_checked": ["OFAC SDN", "UN SC Consolidated List"],
            "sources_note": "EU Financial Sanctions File requires manual verification at webgate.ec.europa.eu/fsd",
        }
    }
