from agent.state import DDState
from integrations.hermes_client import HermesClient

_client = None


def _get_client() -> HermesClient:
    global _client
    if _client is None:
        _client = HermesClient()
    return _client


def hermes_register(state: DDState) -> dict:
    """Register the supplier in Hermes watchlist after DD report is generated."""
    try:
        is_new = _get_client().register_vendor(
            vendor_name=state["company_name"],
            category=state.get("category", ""),
            country=state.get("country", ""),
            source="dd_agent",
        )
        return {"hermes_registered": is_new}
    except Exception:
        return {"hermes_registered": False}
