"""FastAPI — punto único de entrada HTTP del asistente conversacional de Banorte.

Endpoints:
  POST /chat                        — procesa un mensaje y retorna la respuesta del agente
  GET  /health                      — health check del sistema
  GET  /conversations/{conv_id}     — historial de una conversación

El body del POST /chat sigue el contrato exacto del assessment de Banorte.
La persistencia de memoria ocurre dentro del grafo (memory_node), no aquí.
"""

import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app import config  # noqa: F401 — valida OPENAI_API_KEY al importar
from app.database.init_db import init as init_db
from app.graph.graph import agent_graph
from app.memory.conversation import ConversationMemory

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class _ASCIIJSONResponse(JSONResponse):

    def render(self, content: object) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=True,
            allow_nan=False,
            indent=None,
            separators=(",", ":"),
        ).encode("ascii")


# ─── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa la BD al arrancar. No requiere cleanup al cerrar."""
    logger.info("Banorte Agent starting up...")
    init_db()
    logger.info("Database initialized. Ready to serve requests.")
    yield
    logger.info("Banorte Agent shutting down.")


# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Banorte — Agente Conversacional de Políticas Operativas",
    description=(
        "Asistente conversacional interno para empleados de Banorte. "
        "Responde preguntas sobre procesos operativos usando RAG y BD estructurada."
    ),
    version="1.0.0",
    lifespan=lifespan,
    default_response_class=_ASCIIJSONResponse,
)


# ─── Modelos Pydantic ─────────────────────────────────────────────────────────

class MessageBody(BaseModel):
    text: str


class RequestMetadata(BaseModel):
    channel: str = "web"
    timestamp: str = ""


class ChatRequest(BaseModel):
    conversation_id: str
    user_id: str
    message: MessageBody
    metadata: RequestMetadata = RequestMetadata()


class SourceItem(BaseModel):
    content: str
    source: str
    score: float


class ChatResponse(BaseModel):
    conversation_id: str
    response: str
    agent_used: str
    tool_used: str | None
    sources: list[SourceItem]
    timestamp: str


class ConversationMessage(BaseModel):
    role: str
    content: str


class ConversationHistoryResponse(BaseModel):
    conversation_id: str
    history: list[ConversationMessage]
    turn_count: int


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Procesa un mensaje del usuario y retorna la respuesta del agente.

    El grafo LangGraph orquesta la clasificación de intent, el tool calling
    (RAG y/o SQL) y la persistencia de memoria. Este endpoint solo invoca
    el grafo y serializa el resultado.
    """
    logger.info(
        f"POST /chat: conversation_id='{request.conversation_id}' "
        f"user_id='{request.user_id}' "
        f"message='{request.message.text[:60]}'"
    )

    initial_state = {
        "conversation_id": request.conversation_id,
        "user_id": request.user_id,
        "user_message": request.message.text,
        "messages": [],
        "intent": "",
        "response": "",
        "agent_used": "",
        "tool_used": None,
        "sources": [],
    }

    try:
        result = agent_graph.invoke(initial_state)
    except Exception as e:
        logger.error(f"Graph invocation failed for conversation_id='{request.conversation_id}': {e}")
        raise HTTPException(status_code=500, detail="Error interno del agente. Intenta de nuevo.")

    sources = [
        SourceItem(
            content=s.get("content", ""),
            source=s.get("source", ""),
            score=s.get("score", 0.0),
        )
        for s in result.get("sources", [])
    ]

    logger.info(
        f"POST /chat done: conversation_id='{request.conversation_id}' "
        f"agent_used='{result['agent_used']}' "
        f"tool_used='{result['tool_used']}'"
    )

    return ChatResponse(
        conversation_id=request.conversation_id,
        response=result["response"],
        agent_used=result["agent_used"],
        tool_used=result["tool_used"],
        sources=sources,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/health")
async def health() -> dict:
    """Health check — retorna ok si el servidor está en pie."""
    return {"status": "ok"}


@app.get("/conversations/{conversation_id}", response_model=ConversationHistoryResponse)
async def get_conversation(conversation_id: str) -> ConversationHistoryResponse:
    """Retorna el historial completo de una conversación.

    Args:
        conversation_id: ID único de la conversación a consultar.

    Returns:
        Historial con roles user/assistant y conteo de turnos.
    """
    logger.info(f"GET /conversations/{conversation_id}")

    try:
        history = ConversationMemory().get_history(conversation_id)
    except Exception as e:
        logger.error(f"Failed to load history for conversation_id='{conversation_id}': {e}")
        raise HTTPException(status_code=500, detail="Error al recuperar el historial.")

    messages = [ConversationMessage(role=m["role"], content=m["content"]) for m in history]
    # turn_count = número de turnos completos (cada turno = 1 user + 1 assistant)
    turn_count = len(history) // 2

    return ConversationHistoryResponse(
        conversation_id=conversation_id,
        history=messages,
        turn_count=turn_count,
    )
