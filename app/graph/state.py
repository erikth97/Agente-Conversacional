"""Estado compartido del grafo LangGraph.

AgentState es el TypedDict que fluye entre nodos. Cada nodo puede leer
cualquier campo y retornar los campos que modifica.
"""

from typing import Annotated

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class AgentState(TypedDict):
    """Estado compartido entre el orquestador y el especialista.

    Campos:
        conversation_id: ID único de la conversación (de FastAPI).
        user_id: Identificador del usuario.
        user_message: Texto del último mensaje del usuario.
        messages: Historial de mensajes LangChain. El reducer add_messages
                  acumula mensajes sin duplicar por ID.
        intent: Categoría clasificada por el orquestador.
                'operativo'    → delega al especialista
                'fuera_dominio'→ responde mensaje fijo, no delega
                'saludo'       → responde directamente, no delega
        response: Respuesta final que retorna FastAPI al cliente.
        agent_used: Qué agente generó la respuesta ('orchestrator' | 'specialist').
        tool_used: Qué tool(s) usó el especialista ('rag' | 'sql' | 'hybrid' | None).
        sources: Chunks de RAG usados en la respuesta (para trazabilidad).
    """

    conversation_id: str
    user_id: str
    user_message: str
    messages: Annotated[list, add_messages]
    intent: str
    response: str
    agent_used: str
    tool_used: str | None
    sources: list[dict]
