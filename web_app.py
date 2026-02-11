"""Flask web app — submit queries, stream execution events, view reports."""

from __future__ import annotations

import threading

from flask import Flask, Response, jsonify, render_template, request
from langgraph.graph import StateGraph, START, END

import config
import event_bus
from event_bus import Event, EventType
from state import ResearchState
from node_wrappers import search_node, reflect_node, retrieve_node, finalize_node

app = Flask(__name__)

_run_lock = threading.Lock()
_running = False


def _should_continue(state: ResearchState) -> str:
    """Conditional edge: loop back to search or proceed to retrieve."""
    if (
        not state.get("research_complete", False)
        and state.get("iteration", 0) < config.MAX_SEARCH_ITERATIONS
    ):
        return "search"
    return "retrieve"


def _build_web_graph():
    """Assemble the same graph topology as researcher.py but with wrapped nodes."""
    graph = StateGraph(ResearchState)

    graph.add_node("search", search_node)
    graph.add_node("reflect", reflect_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("finalize", finalize_node)

    graph.add_edge(START, "search")
    graph.add_edge("search", "reflect")
    graph.add_conditional_edges(
        "reflect", _should_continue, {"search": "search", "retrieve": "retrieve"}
    )
    graph.add_edge("retrieve", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile()


def _run_graph(query: str) -> None:
    """Execute the research graph in a background thread, emitting events."""
    global _running
    try:
        app_graph = _build_web_graph()

        initial_state: ResearchState = {
            "query": query,
            "messages": [],
            "search_results": [],
            "candidates": [],
            "gaps": [],
            "research_complete": False,
            "iteration": 0,
            "report": "",
        }

        # Run the full graph (events are emitted by the wrapped nodes)
        app_graph.invoke(initial_state)

        event_bus.emit(Event(type=EventType.DONE, node="system", data={}))
    except Exception as e:
        event_bus.emit(Event(
            type=EventType.ERROR,
            node="system",
            data={"error": str(e)},
        ))
        event_bus.emit(Event(type=EventType.DONE, node="system", data={}))
    finally:
        with _run_lock:
            _running = False


@app.route("/")
def index():
    return render_template(
        "index.html",
        tool_model=config.TOOL_MODEL,
        reasoning_model=config.REASONING_MODEL,
        embedding_model=config.EMBEDDING_MODEL,
        max_iterations=config.MAX_SEARCH_ITERATIONS,
    )


@app.route("/run", methods=["POST"])
def run():
    global _running

    data = request.get_json(silent=True) or {}
    query = data.get("query", "").strip()
    if not query:
        return jsonify({"error": "query is required"}), 400

    with _run_lock:
        if _running:
            return jsonify({"error": "A run is already in progress"}), 409
        _running = True

    event_bus.clear()

    thread = threading.Thread(target=_run_graph, args=(query,), daemon=True)
    thread.start()

    return jsonify({"status": "started"})


@app.route("/stream")
def stream():
    def generate():
        for event in event_bus.consume(timeout=2.0):
            if event is None:
                yield ": keepalive\n\n"
            else:
                yield event.to_sse()

    return Response(generate(), mimetype="text/event-stream")


if __name__ == "__main__":
    print(f"Research Agent Web UI")
    print(f"  Tool model:      {config.TOOL_MODEL}")
    print(f"  Reasoning model: {config.REASONING_MODEL}")
    print(f"  Max iterations:  {config.MAX_SEARCH_ITERATIONS}")
    print(f"  http://localhost:5000")
    app.run(debug=False, port=5000, threaded=True)
