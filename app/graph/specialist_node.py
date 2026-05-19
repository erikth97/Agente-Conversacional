"""Nodo especialista del grafo LangGraph.

Responsabilidades:
  1. Clasificar internamente el tipo de query (routing interno — NO visible al usuario)
  2. Ejecutar tools en el orden óptimo según el tipo de query
  3. Validar que los chunks RAG superen RAG_MIN_SCORE antes de usarlos
  4. Sintetizar la respuesta citando la fuente obligatoriamente

Routing interno por tipo de query:
  'DATOS_PUNTUALES' → SQL primero (evita que el threshold RAG bloquee datos estructurados)
  'PROCEDIMIENTO'   → RAG primero (documentos tienen el detalle de políticas)
  'MIXTA'           → ambas tools, LLM decide el orden

Lo que NO hace:
  - Inventar datos, tiempos, áreas o procedimientos
  - Usar chunks con score < RAG_MIN_SCORE
  - Responder preguntas fuera del dominio operativo

Nota sobre RAG_MIN_SCORE:
  El threshold actual es global (0.70). Una mejora futura sería un threshold
  adaptativo por proceso, ya que documentos con distinta densidad semántica
  pueden producir scores legítimamente diferentes ante queries válidas.
  Para este MVP el threshold global es suficiente dado el volumen de documentos.
"""

import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from app import config
from app.graph.state import AgentState
from app.tools.rag_tool import RAGTool
from app.tools.sql_tool import SQLTool

logger = logging.getLogger(__name__)

# ─── Constantes de comportamiento ─────────────────────────────────────────────

_SPECIALIST_SYSTEM_PROMPT = """\
Eres el agente especialista de un asistente conversacional interno de Banorte.
Respondes preguntas de empleados sobre procesos operativos internos.

HERRAMIENTAS DISPONIBLES:
- search_knowledge_base: busca información detallada en documentos de políticas.
  Úsala para procedimientos, pasos, requisitos, excepciones, marcos normativos.
- query_process_database: consulta datos estructurados de procesos en la BD.
  Úsala para área responsable, tiempo de resolución, canal, nivel de criticidad.

REGLAS OBLIGATORIAS — CONTEXTO BANCARIO:

1. SOLO usa información retornada por las herramientas. Nunca inventes datos,
   tiempos, áreas ni procedimientos. Si no hay información disponible, dilo.

2. SIEMPRE inicia tu respuesta citando la fuente:
   "Según la política operativa de [nombre del proceso]..."
   Obligatorio para trazabilidad y auditoría interna.

3. Si las herramientas no retornan información relevante, responde exactamente:
   "No encontré información sobre eso en las políticas operativas internas.
   Por favor consulta con tu área responsable."

4. Responde en español formal. Sé preciso y directo.
   No uses "probablemente", "creo que" o "podría ser" para datos operativos.\
"""

_QUERY_TYPE_PROMPT = """\
Clasifica la consulta de un empleado de Banorte sobre procesos operativos internos.

DATOS_PUNTUALES: La consulta pide datos concretos y estructurados como:
  tiempo de resolución, SLA, cuántos días, área responsable, departamento,
  canal de atención, nivel de criticidad, quién atiende, cuánto demora.

PROCEDIMIENTO: La consulta pide detalle documental o de proceso como:
  pasos del proceso, cómo funciona, política, requisitos, documentos necesarios,
  excepciones, marco normativo, explica el proceso, qué implica.

MIXTA: La consulta requiere tanto datos concretos como detalle de procedimiento.

Responde ÚNICAMENTE con una palabra: DATOS_PUNTUALES, PROCEDIMIENTO, o MIXTA\
"""

_NO_INFO_RESPONSE = (
    "No encontré información sobre eso en las políticas operativas internas. "
    "Por favor consulta con tu área responsable."
)

_MAX_ITERATIONS = 4
_VALID_QUERY_TYPES = {"DATOS_PUNTUALES", "PROCEDIMIENTO", "MIXTA"}

# ─── Lazy singletons ──────────────────────────────────────────────────────────

_rag_tool_instance: RAGTool | None = None
_sql_tool_instance: SQLTool | None = None
_llm_instance: ChatOpenAI | None = None


def _get_rag_tool() -> RAGTool:
    global _rag_tool_instance
    if _rag_tool_instance is None:
        _rag_tool_instance = RAGTool()
    return _rag_tool_instance


def _get_sql_tool() -> SQLTool:
    global _sql_tool_instance
    if _sql_tool_instance is None:
        _sql_tool_instance = SQLTool()
    return _sql_tool_instance


def _get_llm() -> ChatOpenAI:
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = ChatOpenAI(
            model=config.LLM_MODEL,
            temperature=0,
            api_key=config.OPENAI_API_KEY,
        )
    return _llm_instance


# ─── LangChain Tools ──────────────────────────────────────────────────────────

@tool
def search_knowledge_base(query: str) -> str:
    """Busca información en la base de conocimiento de políticas operativas de Banorte.

    Usa esta herramienta para preguntas sobre procedimientos, pasos del proceso,
    requisitos documentales, excepciones, marco normativo o cualquier detalle
    de política interna bancaria.

    Args:
        query: Consulta en lenguaje natural sobre el proceso operativo.

    Returns:
        JSON con los chunks relevantes (content, source, score) y parámetros usados.
    """
    result = _get_rag_tool().search(query)
    valid_chunks = [c for c in result["chunks"] if c["score"] >= config.RAG_MIN_SCORE]

    logger.info(
        f"search_knowledge_base: retrieved={len(result['chunks'])} "
        f"valid={len(valid_chunks)} threshold={config.RAG_MIN_SCORE}"
    )

    return json.dumps(
        {
            "chunks": valid_chunks,
            "total_retrieved": len(result["chunks"]),
            "valid_chunks": len(valid_chunks),
            "params": result["params"],
        },
        ensure_ascii=False,
    )


@tool
def query_process_database(proceso_id: str) -> str:
    """Consulta datos estructurados de un proceso operativo en la base de datos.

    Usa esta herramienta para obtener el área responsable, tiempo de resolución,
    canal de atención y nivel de criticidad de un proceso específico.

    Códigos válidos: A (Aclaraciones), B (Cancelación de Productos),
    C (Escalamiento), D (Actualización de Datos), E (Quejas Internas).

    Args:
        proceso_id: Código del proceso operativo (A, B, C, D o E).

    Returns:
        JSON con los campos del proceso o mensaje de error si no existe.
    """
    result = _get_sql_tool().query(proceso_id)
    logger.info(f"query_process_database: proceso_id='{proceso_id}' found={('error' not in result)}")
    return json.dumps(result, ensure_ascii=False)


_TOOLS = [search_knowledge_base, query_process_database]
_TOOLS_MAP: dict = {t.name: t for t in _TOOLS}


# ─── Routing interno ──────────────────────────────────────────────────────────

def _classify_query_type(user_message: str) -> str:
    """Clasifica el tipo de query para determinar la estrategia de tool calling.

    Esta clasificación es interna al especialista — no es visible al usuario.
    Determina qué tools se invocan primero para evitar que el threshold RAG
    bloquee respuestas que la BD tiene disponibles como datos estructurados.

    Args:
        user_message: Texto de la consulta del usuario.

    Returns:
        'DATOS_PUNTUALES' | 'PROCEDIMIENTO' | 'MIXTA'
    """
    response = _get_llm().invoke([
        SystemMessage(content=_QUERY_TYPE_PROMPT),
        HumanMessage(content=user_message),
    ])
    raw = response.content.strip().upper()

    if raw not in _VALID_QUERY_TYPES:
        logger.warning(f"Query classifier returned unexpected='{raw}', defaulting to MIXTA")
        return "MIXTA"

    logger.info(f"Query classifier: type='{raw}' for message='{user_message[:60]}'")
    return raw


def _run_tool_loop(
    messages: list,
    available_tools: list,
    max_iter: int,
) -> tuple[list, object, list, bool, bool]:
    """Ejecuta el loop de tool calling con las tools disponibles especificadas.

    Args:
        messages: Lista de mensajes LangChain (SystemMessage + historial + user).
        available_tools: Tools que el LLM puede invocar en este loop.
        max_iter: Número máximo de iteraciones antes de forzar el fin.

    Returns:
        Tuple: (messages_updated, last_response, rag_chunks, rag_called, sql_called)
    """
    llm_with_tools = _get_llm().bind_tools(available_tools)
    tools_map = {t.name: t for t in available_tools}

    rag_chunks: list[dict] = []
    rag_called = False
    sql_called = False
    last_response = None

    for iteration in range(max_iter):
        response = llm_with_tools.invoke(messages)
        messages.append(response)
        last_response = response

        logger.info(
            f"Tool loop iteration {iteration + 1}/{max_iter}: "
            f"tool_calls={len(response.tool_calls)} "
            f"has_content={bool(response.content)}"
        )

        if not response.tool_calls:
            break

        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_id = tool_call["id"]
            tool_args = tool_call["args"]

            logger.info(f"Calling tool='{tool_name}' args={tool_args}")

            if tool_name not in tools_map:
                tool_result = json.dumps({"error": f"Tool '{tool_name}' not available in this context"})
            else:
                tool_result = tools_map[tool_name].invoke(tool_args)

            if tool_name == "search_knowledge_base":
                rag_called = True
                rag_chunks = json.loads(tool_result).get("chunks", [])

            elif tool_name == "query_process_database":
                sql_called = True

            messages.append(ToolMessage(content=tool_result, tool_call_id=tool_id))

    else:
        logger.warning(f"Tool loop reached max iterations ({max_iter})")

    return messages, last_response, rag_chunks, rag_called, sql_called


# ─── Nodo del grafo ───────────────────────────────────────────────────────────

def specialist_node(state: AgentState) -> dict:
    """Nodo especialista: pre-clasifica la query, ejecuta tools en orden óptimo
    y sintetiza la respuesta con cita de fuente obligatoria.

    Estrategia por tipo de query:
      DATOS_PUNTUALES → SQL primero (max 2 iter). Sin RAG — evita que el
                        threshold de score bloquee datos que la BD tiene exactos.
      PROCEDIMIENTO   → RAG primero (max 2 iter), luego SQL para complementar
                        datos estructurados si el LLM los necesita (max 2 iter).
      MIXTA           → ambas tools disponibles, LLM decide orden (max 4 iter).

    Args:
        state: Estado del grafo con messages y user_message del orquestador.

    Returns:
        dict con response, agent_used, tool_used y sources actualizados.
    """
    user_message = state["user_message"]

    # ─── 1. Pre-clasificación interna (no visible al usuario) ─────────────────
    query_type = _classify_query_type(user_message)

    # ─── 2. Construir mensajes base ───────────────────────────────────────────
    base_messages: list = [SystemMessage(content=_SPECIALIST_SYSTEM_PROMPT)]
    base_messages += list(state["messages"])

    rag_sources: list[dict] = []
    rag_called = False
    sql_called = False
    last_response = None
    messages = base_messages.copy()

    # ─── 3. Tool calling según tipo de query ──────────────────────────────────

    if query_type == "DATOS_PUNTUALES":
        # SQL only — la BD tiene los datos estructurados exactos.
        # No invocar RAG aquí evita que su threshold bloquee la respuesta.
        logger.info("Specialist routing: DATOS_PUNTUALES → SQL only")
        messages, last_response, _, _, sql_called = _run_tool_loop(
            messages, [query_process_database], max_iter=2
        )

    elif query_type == "PROCEDIMIENTO":
        # RAG primero: los documentos tienen el detalle de la política.
        logger.info("Specialist routing: PROCEDIMIENTO → RAG first, then SQL complement")
        messages, primary_response, rag_sources, rag_called, _ = _run_tool_loop(
            messages, [search_knowledge_base], max_iter=2
        )
        # Segunda pasada: SQL disponible para complementar datos estructurados.
        # Si el LLM no llama SQL (closing remark sin tool_calls), se descarta
        # ese response y se conserva primary_response con su cita de fuente.
        messages, complement_response, _, _, sql_called = _run_tool_loop(
            messages, [query_process_database], max_iter=2
        )
        # Solo usar la respuesta del segundo loop si SQL fue realmente invocado.
        last_response = complement_response if sql_called else primary_response

    else:  # MIXTA
        # Ambas tools disponibles. El LLM decide el orden según el contexto.
        logger.info("Specialist routing: MIXTA → both tools, LLM decides order")
        messages, last_response, rag_sources, rag_called, sql_called = _run_tool_loop(
            messages, _TOOLS, max_iter=_MAX_ITERATIONS
        )

    # ─── 4. Validación: RAG sin chunks válidos y sin SQL como fallback ────────
    if rag_called and not rag_sources and not sql_called:
        logger.warning(
            f"Specialist: RAG returned no valid chunks "
            f"(threshold={config.RAG_MIN_SCORE}) and SQL was not called"
        )
        return {
            "response": _NO_INFO_RESPONSE,
            "agent_used": "specialist",
            "tool_used": "rag",
            "sources": [],
        }

    # ─── 5. Determinar tool_used ──────────────────────────────────────────────
    if rag_called and sql_called:
        tool_used = "hybrid"
    elif rag_called:
        tool_used = "rag"
    elif sql_called:
        tool_used = "sql"
    else:
        tool_used = None

    # ─── 6. Respuesta final ───────────────────────────────────────────────────
    final_response = (
        last_response.content
        if last_response and last_response.content
        else _NO_INFO_RESPONSE
    )

    logger.info(
        f"Specialist: query_type='{query_type}' tool_used='{tool_used}' "
        f"rag_chunks={len(rag_sources)} response_len={len(final_response)}"
    )

    return {
        "response": final_response,
        "agent_used": "specialist",
        "tool_used": tool_used,
        "sources": rag_sources,
    }
