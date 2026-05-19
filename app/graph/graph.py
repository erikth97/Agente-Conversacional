"""Grafo LangGraph — multi-agente Orquestador + Especialista.

Topología:
  START → orchestrator_node
    intent='operativo'    → specialist_node → memory_node → END
    intent='fuera_dominio'→ memory_node → END
    intent='saludo'       → memory_node → END

memory_node siempre es el último nodo antes de END, garantizando que la
memoria persiste independientemente de la capa de transporte (FastAPI o tests).

El grafo compilado se expone como `agent_graph` para su uso en FastAPI.
"""

import logging

from langgraph.graph import END, START, StateGraph

from app.graph.memory_node import memory_node
from app.graph.orchestrator_node import orchestrator_node
from app.graph.specialist_node import specialist_node
from app.graph.state import AgentState

logger = logging.getLogger(__name__)


def _route_from_orchestrator(state: AgentState) -> str:
    """Determina el siguiente nodo según el intent clasificado por el orquestador.

    Returns:
        'specialist' para intent operativo, 'memory' para el resto.
    """
    intent = state["intent"]
    if intent == "operativo":
        logger.info("Router: intent='operativo' → specialist_node")
        return "specialist"

    logger.info(f"Router: intent='{intent}' → memory_node (orchestrator handled directly)")
    return "memory"


def _build_graph() -> StateGraph:
    """Construye y compila el StateGraph con nodos y edges."""
    builder = StateGraph(AgentState)

    # ─── Nodos ────────────────────────────────────────────────────────────────
    builder.add_node("orchestrator", orchestrator_node)
    builder.add_node("specialist", specialist_node)
    builder.add_node("memory", memory_node)

    # ─── Edges ────────────────────────────────────────────────────────────────
    builder.add_edge(START, "orchestrator")

    builder.add_conditional_edges(
        "orchestrator",
        _route_from_orchestrator,
        {
            "specialist": "specialist",
            "memory": "memory",
        },
    )

    # Ambos caminos convergen en memory antes de END
    builder.add_edge("specialist", "memory")
    builder.add_edge("memory", END)

    return builder.compile()


# Grafo compilado — importado por FastAPI en main.py
agent_graph = _build_graph()
logger.info("LangGraph agent_graph compiled and ready")
