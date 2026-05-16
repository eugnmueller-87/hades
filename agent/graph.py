from langgraph.graph import StateGraph, END
from agent.state import DDState
from agent.nodes.hermes_preflight import hermes_preflight
from agent.nodes.web_research import web_research
from agent.nodes.news_sentiment import news_sentiment
from agent.nodes.sanctions_check import sanctions_check
from agent.nodes.registry_lookup import registry_lookup
from agent.nodes.lksg_signals import lksg_signals
from agent.nodes.esg_signals import esg_signals
from agent.nodes.synthesis import synthesis
from agent.nodes.report_generator import report_generator
from agent.nodes.hermes_register import hermes_register


def run_research_nodes(state: DDState) -> DDState:
    """Run all 6 research nodes — executed via parallel Send in the graph."""
    return state


def build_graph():
    g = StateGraph(DDState)

    # Pre-flight: check Hermes before anything else
    g.add_node("hermes_preflight", hermes_preflight)

    # 6 parallel research nodes
    g.add_node("web_research", web_research)
    g.add_node("news_sentiment", news_sentiment)
    g.add_node("sanctions_check", sanctions_check)
    g.add_node("registry_lookup", registry_lookup)
    g.add_node("lksg_signals", lksg_signals)
    g.add_node("esg_signals", esg_signals)

    # Claude reasoning nodes
    g.add_node("synthesis", synthesis)
    g.add_node("report_generator", report_generator)

    # Post-report: register in Hermes
    g.add_node("hermes_register", hermes_register)

    # Entry point
    g.set_entry_point("hermes_preflight")

    # Pre-flight fans out to all 6 research nodes in parallel
    g.add_edge("hermes_preflight", "web_research")
    g.add_edge("hermes_preflight", "news_sentiment")
    g.add_edge("hermes_preflight", "sanctions_check")
    g.add_edge("hermes_preflight", "registry_lookup")
    g.add_edge("hermes_preflight", "lksg_signals")
    g.add_edge("hermes_preflight", "esg_signals")

    # All research nodes converge into synthesis
    g.add_edge("web_research", "synthesis")
    g.add_edge("news_sentiment", "synthesis")
    g.add_edge("sanctions_check", "synthesis")
    g.add_edge("registry_lookup", "synthesis")
    g.add_edge("lksg_signals", "synthesis")
    g.add_edge("esg_signals", "synthesis")

    # Synthesis → report → register → done
    g.add_edge("synthesis", "report_generator")
    g.add_edge("report_generator", "hermes_register")
    g.add_edge("hermes_register", END)

    return g.compile()


# Module-level compiled graph — import and invoke directly
dd_graph = build_graph()
