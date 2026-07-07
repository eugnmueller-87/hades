"""Tests for Hermes registration idempotency (no network).

Previously a 2-line stub. The documented contract is: register_vendor returns True on first
registration, False if the vendor already exists (idempotent — no duplicate watchlist entries).
We inject a fake Redis so the pure logic is tested without a live connection.
"""
from integrations.hermes_client import HermesClient


class _FakeRedis:
    def __init__(self):
        self.store = {}

    def exists(self, key):
        return key in self.store

    def set(self, key, val):
        self.store[key] = val


def _client_with_fake_redis():
    # Bypass __init__ (which connects to Upstash) and inject a fake client.
    c = HermesClient.__new__(HermesClient)
    c.r = _FakeRedis()
    c._slug_cache = None
    return c


def test_first_registration_returns_true():
    c = _client_with_fake_redis()
    assert c.register_vendor("Bechtle AG", "it_hardware") is True


def test_second_registration_is_idempotent_false():
    c = _client_with_fake_redis()
    assert c.register_vendor("Bechtle AG", "it_hardware") is True
    assert c.register_vendor("Bechtle AG", "it_hardware") is False  # already exists


def test_registration_writes_a_watchlist_entry():
    c = _client_with_fake_redis()
    c.register_vendor("Siemens", "it_services", spend_eur=1234.567, country="DE")
    keys = list(c.r.store.keys())
    assert any(k.startswith("hermes:watchlist:") for k in keys)


def test_different_vendors_both_register():
    c = _client_with_fake_redis()
    assert c.register_vendor("Bosch", "it_hardware") is True
    assert c.register_vendor("SAP", "software") is True
