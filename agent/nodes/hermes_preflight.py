from agent.state import DDState
from integrations.hermes_client import HermesClient

_client = None


def _get_client() -> HermesClient:
    global _client
    if _client is None:
        _client = HermesClient()
    return _client


def hermes_preflight(state: DDState) -> dict:
    company = state["company_name"]

    try:
        intel = _get_client().get_vendor_intel(company, limit=10)
    except Exception as e:
        # Hermes unavailable — run all external nodes at full depth
        return {
            "hermes_intel": {"tracked_by_hermes": False, "error": str(e)},
            "hermes_tracked": False,
            "skip_news": False,
        }

    tracked = intel.get("tracked_by_hermes", False)
    signal_count = intel.get("signal_count", 0)

    return {
        "hermes_intel": intel,
        "hermes_tracked": tracked,
        # Skip NewsAPI if Hermes already has strong coverage
        "skip_news": tracked and signal_count > 10,
    }
