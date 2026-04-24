from app.graphs.diet_chat_graph import build_diet_chat_graph, compile_diet_chat_graph_checkpointer_memory


def test_diet_chat_graph_compiles_with_memory_checkpointer() -> None:
    c = compile_diet_chat_graph_checkpointer_memory()
    assert c is not None


def test_diet_chat_graph_has_expected_nodes() -> None:
    g = build_diet_chat_graph()
    nodes = set(g.nodes.keys())
    assert "route_intent" in nodes
    assert "human_confirm" in nodes
    assert "intake_pipeline" in nodes
