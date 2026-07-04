"""
Hermes Client — shared Upstash Redis connection for DD agent.
Same credentials as SpendLens. Requires UPSTASH_REDIS_REST_URL
and UPSTASH_REDIS_REST_TOKEN in .env.
"""

import os
import json
import re
from datetime import datetime
from difflib import get_close_matches
from upstash_redis import Redis

PROCUREMENT_SIGNALS = {
    "SUPPLY_CHAIN",
    "PRICING_CHANGE",
    "EARNINGS",
    "REGULATORY",
    "ACQUISITION",
    "LAYOFFS_HIRING",
}

SIGNAL_TO_CATEGORY = {
    "SUPPLY_CHAIN":    "Hardware & Equipment",
    "PRICING_CHANGE":  "Cloud & Compute",
    "EARNINGS":        "Professional Services",
    "REGULATORY":      "Professional Services",
    "ACQUISITION":     "Cloud & Compute",
    "LAYOFFS_HIRING":  "Recruitment & HR",
    "FUNDING":         "AI/ML APIs & Data",
    "PRODUCT_RELEASE": "Cloud & Compute",
    "PARTNERSHIP":     "Professional Services",
    "RESEARCH_PAPER":  "AI/ML APIs & Data",
    "OTHER":           "Professional Services",
}

SPENDLENS_CATEGORY_TO_HERMES = {
    "Cloud & Compute":          "Cloud & Infrastructure",
    "AI/ML APIs & Data":        "AI Foundation Labs",
    "IT Software & SaaS":       "SaaS & Dev Tools",
    "Telecom & Voice":          "Telecom",
    "Recruitment & HR":         "HR & Talent",
    "Professional Services":    "Professional Services",
    "Marketing & Campaigns":    "Marketing Tech",
    "Facilities & Office":      "Facilities",
    "Real Estate":              "Real Estate",
    "Hardware & Equipment":     "Semiconductors & Chips",
    "Travel & Expenses":        "Travel & Logistics",
}


class HermesClient:
    def __init__(self):
        self.r = Redis(
            url=os.environ["UPSTASH_REDIS_REST_URL"],
            token=os.environ["UPSTASH_REDIS_REST_TOKEN"],
        )
        self._slug_cache = None

    def _slug(self, name: str) -> str:
        slug = name.lower().strip().replace(" ", "_").replace("-", "_").replace(".", "_")
        # Whitelist word chars (unicode-aware, so existing keys like "müller_gmbh"
        # still resolve) — keeps colons/newlines/etc. out of Redis key names —
        # and bound length so arbitrary input can't create huge keys.
        slug = re.sub(r"[^\w]", "_", slug)
        return slug[:100]

    def _known_slugs(self) -> list[str]:
        if self._slug_cache is None:
            keys = self.r.keys("hermes:supplier:*")
            self._slug_cache = [k.replace("hermes:supplier:", "") for k in keys]
        return self._slug_cache

    def _resolve(self, vendor_name: str) -> str | None:
        direct = self._slug(vendor_name)
        if self.r.exists(f"hermes:supplier:{direct}"):
            return direct
        known = self._known_slugs()
        matches = get_close_matches(direct, known, n=1, cutoff=0.6)
        return matches[0] if matches else None

    def _fetch_items(self, slug: str, limit: int) -> list[dict]:
        ids = self.r.lrange(f"hermes:supplier:{slug}", 0, limit - 1)
        items = []
        for item_id in ids:
            raw = self.r.get(f"hermes:item:{item_id}")
            if raw:
                items.append(json.loads(raw))
        return items

    def get_signals(self, vendor_name: str, limit: int = 10, procurement_only: bool = True) -> list[dict]:
        slug = self._resolve(vendor_name)
        if not slug:
            return []
        items = self._fetch_items(slug, limit)
        if procurement_only:
            items = [i for i in items if i.get("signal_type") in PROCUREMENT_SIGNALS]
        return items

    def get_risk_flags(self, vendor_name: str) -> list[dict]:
        items = self.get_signals(vendor_name, limit=20, procurement_only=True)
        return [i for i in items if i.get("is_significant") and i.get("urgency") in ("HIGH", "MEDIUM")]

    def get_vendor_intel(self, vendor_name: str, limit: int = 10) -> dict:
        slug = self._resolve(vendor_name)
        tracked = slug is not None
        signals = self.get_signals(vendor_name, limit=limit, procurement_only=False) if tracked else []
        risk_flags = [s for s in signals if s.get("urgency") in ("HIGH", "MEDIUM") and s.get("is_significant")]
        return {
            "tracked_by_hermes": tracked,
            "hermes_slug": slug,
            "signal_count": len(signals),
            "risk_flags": len(risk_flags),
            "top_signals": [
                {
                    "title": s.get("title", "")[:120],
                    "signal_type": s.get("signal_type"),
                    "urgency": s.get("urgency"),
                    "published": s.get("published", "")[:10],
                    "significance_reason": s.get("significance_reason", "")[:150],
                    "url": s.get("url", ""),
                }
                for s in signals[:limit]
            ],
        }

    def write_audit(self, company_name: str, audit_entry: dict) -> None:
        """
        Append one audit entry to hades:audit:<slug> (Redis list, newest first).
        Keeps the last 50 entries per supplier — older ones are trimmed automatically.
        TTL is refreshed to 2 years on every write so inactive suppliers eventually expire.
        """
        slug = self._slug(company_name)
        key = f"hades:audit:{slug}"
        self.r.lpush(key, json.dumps(audit_entry))
        self.r.ltrim(key, 0, 49)
        self.r.expire(key, 60 * 60 * 24 * 730)  # 2 years, reset on each new investigation

    def get_all_audit_slugs(self) -> list[str]:
        """Return all slugs that have audit records in Redis."""
        keys = self.r.keys("hades:audit:*")
        return [k.replace("hades:audit:", "") for k in keys]

    def get_audit(self, company_name: str) -> list[dict]:
        """
        Return full audit history for a supplier, newest first.
        Returns [] if no audit records exist.
        """
        slug = self._slug(company_name)
        key = f"hades:audit:{slug}"
        raw_entries = self.r.lrange(key, 0, -1)
        if not raw_entries:
            return []
        result = []
        for entry in raw_entries:
            try:
                result.append(json.loads(entry))
            except (json.JSONDecodeError, TypeError):
                pass
        return result

    def register_vendor(self, vendor_name: str, category: str, spend_eur: float = 0,
                        country: str = "", source: str = "dd_agent") -> bool:
        """
        Register vendor in Hermes watchlist so crawlers start covering it.
        Returns True if newly registered, False if already existed (idempotent).
        """
        slug = self._slug(vendor_name)
        watchlist_key = f"hermes:watchlist:{slug}"
        if self.r.exists(watchlist_key):
            return False
        hermes_category = SPENDLENS_CATEGORY_TO_HERMES.get(category, category)
        entry = {
            "name": vendor_name,
            "slug": slug,
            "category": hermes_category,
            "spend_eur": round(spend_eur, 2),
            "country": country,
            "source": source,
            "registered_at": datetime.utcnow().isoformat(),
        }
        self.r.set(watchlist_key, json.dumps(entry))
        self._slug_cache = None
        return True
