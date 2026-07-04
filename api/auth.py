"""
API-key authentication for cost-bearing and data-exposing endpoints.

One or more keys are read from HADES_API_KEY (comma-separated for multiple
consumers, e.g. Icarus + SpendLens). Callers present a key in the X-API-Key
header. Comparison is constant-time (hmac.compare_digest) to avoid timing
leaks.

If HADES_API_KEY is unset the API runs OPEN (auth disabled) and logs a
warning at import time — this keeps local dev and existing deployments
working until a key is provisioned. /health is never protected.
"""

import hmac
import logging
import os

from fastapi import Header, HTTPException

logger = logging.getLogger("hades.auth")


def _load_keys() -> set[str]:
    raw = os.environ.get("HADES_API_KEY", "")
    return {k.strip() for k in raw.split(",") if k.strip()}


_API_KEYS = _load_keys()

if not _API_KEYS:
    logger.warning(
        "HADES_API_KEY is not set — API authentication is DISABLED. "
        "All endpoints are publicly reachable. Set HADES_API_KEY to enable auth."
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
    FastAPI dependency. Rejects the request with 401 unless a valid key is
    presented in the X-API-Key header. No-op when auth is disabled (no keys
    configured).
    """
    if not _API_KEYS:
        return  # auth disabled — see module-level warning
    if not x_api_key or not _key_valid(x_api_key):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
