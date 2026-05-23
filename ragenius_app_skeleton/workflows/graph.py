"""LangGraph assembly per RAGenius workflow blueprint (stub-only)."""

from __future__ import annotations

from typing import Any

from .graph_state import GraphState
from .nodes import (
    answer,
    evidence_analysis,
    evidence_postprocess,
    execute_turn_plan,
    extract_config_pdf,
    load_or_generate_adapter,
    load_session_context,
    load_template_registry,
    persist_run,
    planner,
    retrieve,
)

try:
    from langgraph.graph import END, StateGraph
except ImportError:  # pragma: no cover
    END = "END"  # type: ignore[assignment]

    class StateGraph:  # type: ignore[no-redef]
        """Minimal fallback graph executor when langgraph is unavailable."""

        def __init__(self, *_: Any, **__: Any) -> None:
            self._nodes = {}
            self._edges = {}
            self._entry = None

        def add_node(self, name: str, fn):
            self._nodes[name] = fn

        def set_entry_point(self, name: str):
            self._entry = name

        def add_edge(self, src: str, dst: str):
            self._edges[src] = dst

        def compile(self):
            nodes = self._nodes
            edges = self._edges
            entry = self._entry

            class _Compiled:
                def invoke(self, state):
                    cursor = entry
                    out = state
                    while cursor and cursor != END:
                        out = nodes[cursor](out)
                        cursor = edges.get(cursor)
                    return out

            return _Compiled()


def build_graph():
    """Construct and compile the workflow graph using stub nodes.

    TODO: Replace stub node behavior with real workflow implementations.
    """
    graph = StateGraph(GraphState)  # type: ignore[arg-type]

    graph.add_node("load_session_context", load_session_context.run)  # type: ignore[arg-type]
    graph.add_node("extract_config_pdf", extract_config_pdf.run)  # type: ignore[arg-type]
    graph.add_node("load_or_generate_adapter", load_or_generate_adapter.run)  # type: ignore[arg-type]
    graph.add_node("load_template_registry", load_template_registry.run)  # type: ignore[arg-type]
    graph.add_node("planner", planner.run)  # type: ignore[arg-type]
    graph.add_node("retrieve", retrieve.run)  # type: ignore[arg-type]
    graph.add_node("execute_turn_plan", execute_turn_plan.run)  # type: ignore[arg-type]
    graph.add_node("evidence_postprocess", evidence_postprocess.run)  # type: ignore[arg-type]
    graph.add_node("evidence_analysis", evidence_analysis.run)  # type: ignore[arg-type]
    graph.add_node("answer", answer.run)  # type: ignore[arg-type]
    graph.add_node("persist_run", persist_run.run)  # type: ignore[arg-type]

    graph.set_entry_point("load_session_context")
    graph.add_edge("load_session_context", "extract_config_pdf")
    graph.add_edge("extract_config_pdf", "load_or_generate_adapter")
    graph.add_edge("load_or_generate_adapter", "load_template_registry")
    graph.add_edge("load_template_registry", "planner")
    graph.add_edge("planner", "retrieve")
    graph.add_edge("retrieve", "execute_turn_plan")
    graph.add_edge("execute_turn_plan", "evidence_postprocess")
    graph.add_edge("evidence_postprocess", "evidence_analysis")
    graph.add_edge("evidence_analysis", "answer")
    graph.add_edge("answer", "persist_run")
    graph.add_edge("persist_run", END)

    return graph.compile()
