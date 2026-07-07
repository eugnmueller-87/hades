"""Tests for fail-closed API-key auth (api/auth.py).

The rule under test: a compliance-facing service must NEVER run open by accident. A missing
HADES_API_KEY fails CLOSED (503); the only way to run without auth is the explicit, loud
HADES_ALLOW_NO_AUTH opt-in for local dev. A valid key passes; an invalid/missing one 401s.

auth.py reads env at import time, so each test reloads the module under a patched environment.
"""
import importlib
import os

import pytest
from fastapi import HTTPException


def _reload_auth(monkeypatch, *, api_key=None, allow_no_auth=None):
    monkeypatch.delenv("HADES_API_KEY", raising=False)
    monkeypatch.delenv("HADES_ALLOW_NO_AUTH", raising=False)
    if api_key is not None:
        monkeypatch.setenv("HADES_API_KEY", api_key)
    if allow_no_auth is not None:
        monkeypatch.setenv("HADES_ALLOW_NO_AUTH", allow_no_auth)
    import api.auth as auth
    return importlib.reload(auth)


def test_missing_key_fails_closed_with_503(monkeypatch):
    # No key, no opt-out → the service must refuse (503), NOT run open.
    auth = _reload_auth(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        auth.require_api_key(x_api_key=None)
    assert exc.value.status_code == 503


def test_missing_key_rejects_even_with_a_presented_key(monkeypatch):
    # If no keys are configured, no presented value can be valid — still 503.
    auth = _reload_auth(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        auth.require_api_key(x_api_key="anything")
    assert exc.value.status_code == 503


def test_explicit_opt_out_allows_no_auth(monkeypatch):
    # The deliberate local-dev switch — and only this — permits open running.
    auth = _reload_auth(monkeypatch, allow_no_auth="1")
    assert auth.require_api_key(x_api_key=None) is None


def test_valid_key_passes(monkeypatch):
    auth = _reload_auth(monkeypatch, api_key="secret-key-123")
    assert auth.require_api_key(x_api_key="secret-key-123") is None


def test_invalid_key_401s(monkeypatch):
    auth = _reload_auth(monkeypatch, api_key="secret-key-123")
    with pytest.raises(HTTPException) as exc:
        auth.require_api_key(x_api_key="wrong-key")
    assert exc.value.status_code == 401


def test_missing_header_401s_when_key_configured(monkeypatch):
    auth = _reload_auth(monkeypatch, api_key="secret-key-123")
    with pytest.raises(HTTPException) as exc:
        auth.require_api_key(x_api_key=None)
    assert exc.value.status_code == 401


def test_multiple_keys_all_valid(monkeypatch):
    auth = _reload_auth(monkeypatch, api_key="icarus-key, spendlens-key")
    assert auth.require_api_key(x_api_key="icarus-key") is None
    assert auth.require_api_key(x_api_key="spendlens-key") is None


def teardown_module(module):
    # Leave auth module in a clean state for any later importer.
    import api.auth
    importlib.reload(api.auth)
