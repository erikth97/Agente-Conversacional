"""Nodo orquestador del grafo LangGraph.

Responsabilidades:
  1. Cargar historial de conversación desde SQLite
  2. Clasificar el intent del usuario (temperature=0 — determinista)
  3. Para intents no operativos, generar respuesta directa sin delegar
  4. Para intent 'operativo', preparar el estado para el especialista

Lo que NO hace:
  - Llamar a RAGTool ni SQLTool
  - Inventar información sobre procesos
  - Responder preguntas operativas directamente
"""

import logging

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app import config
from app.graph.state import AgentState
from app.memory.conversation import ConversationMemory

logger = logging.getLogger(__name__)

# ─── Constantes de comportamiento ─────────────────────────────────────────────

_ORCHESTRATOR_SYSTEM_PROMPT = """\
Eres el orquestador de un asistente conversacional interno de Banorte para empleados.
Tu única función es clasificar el mensaje del usuario en UNA de estas tres categorías:

OPERATIVO: Pregunta sobre procesos operativos internos de Banorte:
  aclaraciones de cargos, cancelación de productos bancarios, escalamiento de
  incidencias, actualización de datos del cliente, gestión de quejas internas,
  o cualquier aspecto de estos procesos: tiempos, áreas, canales, procedimientos,
  requisitos, roles, excepciones, marcos normativos.

FUERA_DOMINIO: Pregunta no relacionada con los procesos operativos de Banorte.
  Ejemplos: clima, noticias, geografía, historia, entretenimiento, recetas,
  preguntas generales de conocimiento.

SALUDO: Saludo, despedida o conversación casual sin solicitud operativa.
  Ejemplos: "hola", "buenos días", "gracias", "hasta luego", "¿cómo estás?".

Responde ÚNICAMENTE con una de estas tres palabras: OPERATIVO, FUERA_DOMINIO, SALUDO
Sin puntuación, sin explicaciones, sin texto adicional.\
"""

_GREETING_SYSTEM_PROMPT = """\
Eres un asistente interno de Banorte. Responde saludos de forma breve y profesional.
Menciona que puedes ayudar con los cinco procesos operativos internos: aclaraciones,
cancelación de productos, escalamiento de incidencias, actualización de datos del
cliente y gestión de quejas internas. Sé cordial y conciso (máximo 2 oraciones).\
"""

FUERA_DOMINIO_RESPONSE = (
    "Este asistente está diseñado exclusivamente para consultas sobre "
    "procesos operativos internos de Banorte. "
    "¿En qué proceso puedo ayudarte?"
)

_VALID_INTENTS = {"OPERATIVO", "FUERA_DOMINIO", "SALUDO"}

# ─── Lazy singleton del LLM ───────────────────────────────────────────────────

_llm: ChatOpenAI | None = None


def _get_llm() -> ChatOpenAI:
    """Retorna instancia singleton del LLM con temperature=0."""
    global _llm
    if _llm is None:
        _llm = ChatOpenAI(
            model=config.LLM_MODEL,
            temperature=0,
            api_key=config.OPENAI_API_KEY,
        )
    return _llm


# ─── Helpers privados ─────────────────────────────────────────────────────────

def _load_history_as_messages(conversation_id: str) -> list:
    """Carga el historial de SQLite y lo convierte a mensajes LangChain."""
    memory = ConversationMemory()
    history = memory.get_history(conversation_id)

    messages = []
    for entry in history:
        if entry["role"] == "user":
            messages.append(HumanMessage(content=entry["content"]))
        else:
            messages.append(AIMessage(content=entry["content"]))
    return messages


def _classify_intent(user_message: str, history_messages: list) -> str:
    """Clasifica el intent del usuario. Retorna 'operativo', 'fuera_dominio' o 'saludo'."""
    classification_messages = [
        SystemMessage(content=_ORCHESTRATOR_SYSTEM_PROMPT),
        *history_messages,
        HumanMessage(content=user_message),
    ]
    response = _get_llm().invoke(classification_messages)
    raw = response.content.strip().upper()

    if raw not in _VALID_INTENTS:
        # Fallback seguro: si el LLM responde algo inesperado, asumimos operativo
        # para no bloquear preguntas legítimas. Se loguea para monitoreo.
        logger.warning(f"Orchestrator: unexpected intent response='{raw}', defaulting to 'operativo'")
        return "operativo"

    intent_map = {"OPERATIVO": "operativo", "FUERA_DOMINIO": "fuera_dominio", "SALUDO": "saludo"}
    return intent_map[raw]


def _generate_greeting_response(user_message: str) -> str:
    """Genera respuesta corta y profesional para saludos."""
    response = _get_llm().invoke([
        SystemMessage(content=_GREETING_SYSTEM_PROMPT),
        HumanMessage(content=user_message),
    ])
    return response.content


# ─── Nodo del grafo ───────────────────────────────────────────────────────────

def orchestrator_node(state: AgentState) -> dict:
    """Nodo orquestador: clasifica intent y gestiona respuestas no operativas.

    Args:
        state: Estado actual del grafo con conversation_id y user_message.

    Returns:
        dict con los campos del estado actualizados.
    """
    conversation_id = state["conversation_id"]
    user_message = state["user_message"]

    logger.info(f"Orchestrator: conversation_id='{conversation_id}' processing message")

    # 1. Cargar historial para contexto de clasificación
    history_messages = _load_history_as_messages(conversation_id)
    logger.info(f"Orchestrator: loaded {len(history_messages)} messages from history")

    # 2. Clasificar intent
    intent = _classify_intent(user_message, history_messages)
    logger.info(f"Orchestrator: conversation_id='{conversation_id}' intent='{intent}'")

    # 3. Preparar mensajes de contexto para el especialista (si aplica)
    context_messages = history_messages + [HumanMessage(content=user_message)]

    # 4. Para intents no operativos, responder directamente
    if intent == "fuera_dominio":
        return {
            "messages": context_messages,
            "intent": intent,
            "response": FUERA_DOMINIO_RESPONSE,
            "agent_used": "orchestrator",
            "tool_used": None,
            "sources": [],
        }

    if intent == "saludo":
        greeting = _generate_greeting_response(user_message)
        return {
            "messages": context_messages,
            "intent": intent,
            "response": greeting,
            "agent_used": "orchestrator",
            "tool_used": None,
            "sources": [],
        }

    # 5. Intent operativo: preparar estado para el especialista
    return {
        "messages": context_messages,
        "intent": intent,
        "response": "",
        "agent_used": "orchestrator",
        "tool_used": None,
        "sources": [],
    }
