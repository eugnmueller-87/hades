"""Tests that the DD graph assembles correctly (structure only — no network, no LLM).

Previously a 2-line stub. A broken graph wiring (missing node, wrong entry point, a research
node not fanned out) silently drops a compliance dimension, so pinning the topology matters.

Skips cleanly if langgraph isn't installed (it's a deploy dependency) — runs in CI where the
full requirements are present.
"""
import pytest

pytest.importorskip("langgraph", reason="langgraph is a deploy dependency; graph tests run in CI")

from agent.graph import build_graph  # noqa: E402

_EXPECTED_NODES = {
    "hermes_preflight",
    "web_research", "news_sentiment", "sanctions_check",
    "registry_lookup", "lksg_signals", "esg_signals",
    "synthesis", "report_generator",
    "hermes_register", "audit_writer",
}


def test_graph_builds():
    g = build_graph()
    assert g is not None


def test_graph_has_all_nodes():
    g = build_graph()
    nodes = set(g.nodes.keys())
    missing = _EXPECTED_NODES - nodes
    assert not missing, f"graph is missing nodes: {missing}"


def test_graph_has_the_six_research_dimensions():
    # All 6 risk dimensions must be present — dropping one silently loses a compliance signal.
    g = build_graph()
    nodes = set(g.nodes.keys())
    for research in ["web_research", "news_sentiment", "sanctions_check",
                     "registry_lookup", "lksg_signals", "esg_signals"]:
        assert research in nodes
