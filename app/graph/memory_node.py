"""Nodo de persistencia de memoria conversacional.

Responsabilidad única: persistir el turno actual (user_message + response)
en SQLite antes de que el grafo termine. Se ejecuta en TODOS los caminos
del grafo (operativo y no operativo) garantizando que la memoria persiste
independientemente de la capa de transporte (FastAPI, tests directos, etc.).
"""

import logging

from app.graph.state import AgentState
from app.memory.conversation import ConversationMemory

logger = logging.getLogger(__name__)


def memory_node(state: AgentState) -> dict:
    """Persiste el turno actual en conversation_history antes de END.

    Args:
        state: Estado final del grafo con conversation_id, user_message
               y response ya generados.

    Returns:
        dict vacío — no modifica el estado, solo persiste en SQLite.
    """
    conversation_id = state["conversation_id"]
    user_message = state["user_message"]
    response = state["response"]

    if not response:
        logger.warning(f"memory_node: empty response for conversation_id='{conversation_id}', skipping persist")
        return {}

    ConversationMemory().add_turn(conversation_id, user_message, response)
    logger.info(f"memory_node: turn persisted for conversation_id='{conversation_id}'")
    return {}
