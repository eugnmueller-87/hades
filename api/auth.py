"""
API-key authentication for cost-bearing and data-exposing endpoints.

One or more keys are read from HADES_API_KEY (comma-separated for multiple
consumers, e.g. Icarus + SpendLens). Callers present a key in the X-API-Key
header. Comparison is constant-time (hmac.compare_digest) to avoid timing
leaks.

FAIL-CLOSED BY DEFAULT: if HADES_API_KEY is unset the API rejects every
protected request with 503 — it does NOT run open. This is a compliance-facing
due-diligence service; an accidentally-unset key must never silently expose
investigations. To run without auth (local dev only) you must OPT IN explicitly
by setting HADES_ALLOW_NO_AUTH=1 — a deliberate, loud switch that can never be
tripped by simply forgetting to provision a key. /health is never protected.
"""

import hmac
import logging
import os

from fastapi import Header, HTTPException

logger = logging.getLogger("hades.auth")


def _load_keys() -> set[str]:
    raw = os.environ.get("HADES_API_KEY", "")
    return {k.strip() for k in raw.split(",") if k.strip()}


def _auth_explicitly_disabled() -> bool:
    return os.environ.get("HADES_ALLOW_NO_AUTH", "").strip().lower() in ("1", "true", "yes")


_API_KEYS = _load_keys()
_NO_AUTH = _auth_explicitly_disabled()

if _NO_AUTH:
    logger.warning(
        "HADES_ALLOW_NO_AUTH is set — API authentication is EXPLICITLY DISABLED "
        "(local-dev opt-in). All protected endpoints are publicly reachable. "
        "NEVER set this in a deployed environment."
    )
elif not _API_KEYS:
    logger.error(
        "HADES_API_KEY is not set and HADES_ALLOW_NO_AUTH is not set — protected "
        "endpoints will return 503 (fail-closed). Provision HADES_API_KEY to enable "
        "the service, or set HADES_ALLOW_NO_AUTH=1 for local dev."
    )


def _key_valid(candidate: str) -> bool:
    # Compare against every configured key in constant time. Iterating all keys
    # (rather than short-circuiting) keeps the check independent of which key
    # matched; compare_digest itself guards against per-key timing leaks.
    valid = False
    for key in _API_KEYS:
        if hmac.compare_digest(candidate, key):
            valid = True
    return valid


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """
    FastAPI dependency. Fail-closed:
      - HADES_ALLOW_NO_AUTH set  -> no-op (explicit local-dev opt-out).
      - no keys configured       -> 503 (misconfiguration; never silently open).
      - key configured           -> 401 unless a valid X-API-Key is presented.
    """
    if _NO_AUTH:
        return  # explicit local-dev opt-out — see module-level warning
    if not _API_KEYS:
        # Fail CLOSED: a missing key is a misconfiguration, not an invitation.
        raise HTTPException(
            status_code=503,
            detail="Service unavailable: authentication is not configured.",
        )
    if not x_api_key or not _key_valid(x_api_key):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
