from typing import Any
from typing_extensions import TypedDict


class DDState(TypedDict):
    company_name: str
    category: str
    country: str
    is_recheck: bool
    # Hermes pre-flight
    hermes_intel: dict
    hermes_tracked: bool
    skip_news: bool
    # Research node outputs
    web_results: list[dict]
    news_results: list[dict]
    sanctions_result: dict
    registry_result: dict
    lksg_signals: list[dict]
    esg_signals: list[dict]
    # Synthesis + report
    risk_scores: dict
    report: dict
    # Post-actions
    hermes_registered: bool
