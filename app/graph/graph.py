"""Grafo LangGraph — multi-agente Orquestador + Especialista.

Topología:
  START → orchestrator_node
    intent='operativo'    → specialist_node → END
    intent='fuera_dominio'→ END  (respuesta fija del orquestador)
    intent='saludo'       → END  (respuesta directa del orquestador)

El grafo compilado se expone como `agent_graph` para su uso en FastAPI.
"""

import logging

from langgraph.graph import END, START, StateGraph

from app.graph.orchestrator_node import orchestrator_node
from app.graph.specialist_node import specialist_node
from app.graph.state import AgentState

logger = logging.getLogger(__name__)


def _route_from_orchestrator(state: AgentState) -> str:
    """Determina el siguiente nodo según el intent clasificado por el orquestador.

    Args:
        state: Estado actual con el campo 'intent' ya seteado.

    Returns:
        Nombre del siguiente nodo ('specialist') o END.
    """
    intent = state["intent"]
    if intent == "operativo":
        logger.info("Router: intent='operativo' → specialist_node")
        return "specialist"

    logger.info(f"Router: intent='{intent}' → END (orchestrator handles directly)")
    return END


def _build_graph() -> StateGraph:
    """Construye y compila el StateGraph con nodos y edges."""
    builder = StateGraph(AgentState)

    # ─── Nodos ────────────────────────────────────────────────────────────────
    builder.add_node("orchestrator", orchestrator_node)
    builder.add_node("specialist", specialist_node)

    # ─── Edges ────────────────────────────────────────────────────────────────
    builder.add_edge(START, "orchestrator")

    builder.add_conditional_edges(
        "orchestrator",
        _route_from_orchestrator,
        {
            "specialist": "specialist",
            END: END,
        },
    )

    builder.add_edge("specialist", END)

    return builder.compile()


# Grafo compilado — importado por FastAPI en main.py
agent_graph = _build_graph()
logger.info("LangGraph agent_graph compiled and ready")
