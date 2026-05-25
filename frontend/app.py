"""Frontend Streamlit — Agente Conversacional Banorte.

UI de chat que consume el API FastAPI del agente.
Identidad corporativa: #EC0029, #F5F5F5, #C7C9C9, #6A6867.

Variables de entorno:
    API_URL — URL base de la API FastAPI (default: http://localhost:8000)

Uso:
    streamlit run frontend/app.py
"""

import datetime
import logging
import os
import uuid

import requests
import streamlit as st

logger = logging.getLogger(__name__)

BASE_URL: str = os.getenv("API_URL", "http://localhost:8000")

# ─── Page config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Agente Conversacional",
    page_icon="frontend/assets/banorte_header.svg",
    layout="wide",
)

# ─── CSS Corporativo Banorte ──────────────────────────────────────────────────

_CSS = """
<style>
    [data-testid="stSidebar"] {
        border-right: 4px solid #EC0029;
        background-color: #F5F5F5 !important;
    }

    .stButton > button {
        background-color: #EC0029;
        color: #ffffff;
        border: none;
        border-radius: 3px;
        font-weight: 600;
    }
    .stButton > button:hover {
        background-color: #c4001f;
        color: #ffffff;
    }

    .banorte-title {
        color: #EC0029;
        font-size: 1.8rem;
        font-weight: 800;
        letter-spacing: 3px;
        text-transform: uppercase;
        margin-bottom: 2px;
    }
    .banorte-subtitle {
        color: #6A6867;
        font-size: 0.82rem;
        margin-top: 0;
        letter-spacing: 0.3px;
    }

    .badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 3px;
        font-size: 0.75rem;
        font-weight: 700;
        letter-spacing: 0.8px;
        text-transform: uppercase;
    }
    .badge-orchestrator { background-color: #6A6867; color: #ffffff; }
    .badge-specialist   { background-color: #EC0029; color: #ffffff; }
    .badge-rag          { background-color: #C7C9C9; color: #333333; }
    .badge-sql          { background-color: #6A6867; color: #ffffff; }
    .badge-hybrid       { background-color: #EC0029; color: #ffffff; }
    .badge-none         { background-color: #F5F5F5; color: #6A6867; border: 1px solid #C7C9C9; }

    .detail-label {
        font-size: 0.72rem;
        color: #6A6867;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        font-weight: 600;
        margin-bottom: 6px;
    }
    .source-row {
        font-size: 0.82rem;
        color: #333333;
        padding: 4px 0;
        border-bottom: 1px solid #C7C9C9;
    }
    .source-score {
        color: #EC0029;
        font-weight: 700;
    }
</style>
"""

# ─── Constantes de presentación ───────────────────────────────────────────────

_AGENT_BADGE: dict[str, str] = {
    "orchestrator": "badge-orchestrator",
    "specialist":   "badge-specialist",
}

_TOOL_META: dict = {
    "rag":    ("RAG",       "badge-rag"),
    "sql":    ("SQL",       "badge-sql"),
    "hybrid": ("RAG + SQL", "badge-hybrid"),
    None:     ("—",         "badge-none"),
}


# ─── Estado de sesión ─────────────────────────────────────────────────────────

def _init_session() -> None:
    """Inicializa session_state en el primer render."""
    if "conversation_id" not in st.session_state:
        st.session_state.conversation_id = str(uuid.uuid4())
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "user_id" not in st.session_state:
        st.session_state.user_id = "empleado"


def _new_conversation() -> None:
    """Genera nuevo conversation_id y limpia el historial visual."""
    st.session_state.conversation_id = str(uuid.uuid4())
    st.session_state.messages = []


def _load_conversation(conversation_id: str) -> bool:
    """Carga historial desde GET /conversations/{id}.

    Returns:
        True si se cargó historial, False si no existe o está vacío.
    """
    try:
        resp = requests.get(
            f"{BASE_URL}/conversations/{conversation_id}",
            timeout=10,
        )
        if resp.status_code != 200:
            return False
        data = resp.json()
        history = data.get("history", [])
        if not history:
            return False
        st.session_state.messages = [
            {"role": msg["role"], "content": msg["content"], "metadata": None}
            for msg in history
        ]
        st.session_state.conversation_id = conversation_id
        return True
    except Exception as e:
        logger.error(f"GET /conversations failed: {e}")
        return False


# ─── API helpers ──────────────────────────────────────────────────────────────

def _check_health() -> bool:
    """Ping a /health. Retorna True si el servidor responde."""
    try:
        resp = requests.get(f"{BASE_URL}/health", timeout=3)
        return resp.status_code == 200
    except Exception:
        return False


def _send_message(user_message: str) -> dict | None:
    """POST /chat con el mensaje del usuario.

    Returns:
        dict con response, agent_used, tool_used, sources — o None si falla.
    """
    payload = {
        "conversation_id": st.session_state.conversation_id,
        "user_id": st.session_state.user_id,
        "message": {"text": user_message},
        "metadata": {
            "channel": "streamlit",
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        },
    }
    try:
        resp = requests.post(f"{BASE_URL}/chat", json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"POST /chat failed: {e}")
        return None


# ─── Helpers de renderizado ───────────────────────────────────────────────────

def _badge(label: str, css_class: str) -> str:
    return f'<span class="badge {css_class}">{label}</span>'


def _render_metadata_expander(metadata: dict) -> None:
    """Expander colapsado: agent_used, tool_used, turno y contexto de la herramienta."""
    agent = metadata.get("agent_used", "—")
    tool  = metadata.get("tool_used")
    sources = metadata.get("sources", [])
    turn = len(st.session_state.messages) // 2

    agent_css            = _AGENT_BADGE.get(agent, "badge-none")
    tool_label, tool_css = _TOOL_META.get(tool, (str(tool), "badge-none"))

    with st.expander("Trazabilidad", expanded=False):
        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown('<div class="detail-label">Agente</div>', unsafe_allow_html=True)
            st.markdown(_badge(agent, agent_css), unsafe_allow_html=True)

        with col2:
            st.markdown('<div class="detail-label">Herramienta</div>', unsafe_allow_html=True)
            st.markdown(_badge(tool_label, tool_css), unsafe_allow_html=True)

        with col3:
            st.markdown('<div class="detail-label">Turno</div>', unsafe_allow_html=True)
            st.markdown(
                f'<span style="font-size:0.9rem;font-weight:700;color:#6A6867;">{turn}</span>',
                unsafe_allow_html=True,
            )

        st.markdown("<br>", unsafe_allow_html=True)

        if tool in ("rag", "hybrid") and sources:
            st.markdown('<div class="detail-label">Fuentes RAG</div>', unsafe_allow_html=True)
            for src in sources:
                name  = src.get("source", "—")
                score = src.get("score", 0.0)
                st.markdown(
                    f'<div class="source-row">{name}'
                    f'&nbsp;&nbsp;<span class="source-score">{score:.2f}</span></div>',
                    unsafe_allow_html=True,
                )
        elif tool == "sql":
            st.markdown('<div class="detail-label">Datos estructurados (SQLite)</div>', unsafe_allow_html=True)
            st.caption(
                "Respuesta generada desde la base de datos operativa. "
                "Los datos incluyen \u00e1rea responsable, tiempo de resoluci\u00f3n, "
                "canal de atenci\u00f3n y nivel de criticidad del proceso."
            )
        elif tool is None:
            st.markdown('<div class="detail-label">Fuente</div>', unsafe_allow_html=True)
            st.caption(
                "Respuesta directa del orquestador. "
                "No se consultaron herramientas externas."
            )


def _render_chat_history() -> None:
    """Re-renderiza el historial completo desde session_state.messages."""
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
        # Expander fuera del chat_message para que no quede dentro del bubble
        if msg["role"] == "assistant" and msg.get("metadata"):
            _render_metadata_expander(msg["metadata"])


# ─── Sidebar ──────────────────────────────────────────────────────────────────

def _render_sidebar() -> None:
    with st.sidebar:
        st.image("frontend/assets/banorte_header.svg", width=160)
        st.markdown(
            '<div class="banorte-subtitle">Asistente de Políticas Operativas Internas</div>',
            unsafe_allow_html=True,
        )
        st.divider()

        # Estado del servidor
        if _check_health():
            st.markdown(
                '<span style="color:#EC0029;font-weight:700;font-size:0.85rem;">'
                "&#9679; Servidor activo</span>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<span style="color:#6A6867;font-weight:700;font-size:0.85rem;">'
                f"&#9679; Servidor no disponible</span>"
                f'<br><span style="font-size:0.75rem;color:#6A6867;">{BASE_URL}</span>',
                unsafe_allow_html=True,
            )
        st.caption(
            "Procesos disponibles: Aclaraciones · "
            "Cancelaciones · Escalamiento · "
            "Actualizaci\u00f3n de datos · Quejas"
        )

        st.divider()

        # User ID editable
        new_uid = st.text_input(
            "Usuario",
            value=st.session_state.user_id,
            help="Identificador del usuario para esta sesión.",
        )
        if new_uid != st.session_state.user_id:
            st.session_state.user_id = new_uid

        st.divider()

        # Conversation ID (editable — permite cargar conversaciones anteriores)
        st.markdown('<div class="detail-label">Conversación activa</div>', unsafe_allow_html=True)
        conv_id_input = st.text_input(
            label="conv_id",
            value=st.session_state.conversation_id,
            label_visibility="collapsed",
            help="Pega un ID anterior para retomar una conversación.",
        )
        st.caption(f"Turno {len(st.session_state.messages) // 2}")

        if st.button("Cargar conversación", use_container_width=True):
            if _load_conversation(conv_id_input):
                st.success(f"Conversación cargada — {len(st.session_state.messages) // 2} turnos")
                st.rerun()
            else:
                st.warning("No se encontró historial para ese ID")

        if st.button("Nueva conversación", use_container_width=True):
            _new_conversation()
            st.rerun()


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
    _init_session()
    _render_sidebar()

    # Header
    st.markdown('<div class="banorte-title">Agente Conversacional</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="banorte-subtitle">'
        "Consulta interna de procesos operativos — aclaraciones, cancelaciones, "
        "escalamiento, actualizaci\u00f3n de datos, quejas"
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown("<br>", unsafe_allow_html=True)

    _render_chat_history()

    metadata: dict | None = None
    result: dict | None = None

    if prompt := st.chat_input("Escribe tu consulta..."):
        # Guardar y renderizar mensaje del usuario
        st.session_state.messages.append({"role": "user", "content": prompt, "metadata": None})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Llamar al agente y renderizar respuesta
        with st.chat_message("assistant"):
            with st.spinner("Procesando consulta..."):
                result = _send_message(prompt)

            if result is None:
                error_text = (
                    "No se pudo conectar con el servidor. "
                    f"Verifica que la API est\u00e1 activa en {BASE_URL}."
                )
                st.markdown(error_text)
                st.session_state.messages.append(
                    {"role": "assistant", "content": error_text, "metadata": None}
                )
            else:
                response_text = result.get("response", "Sin respuesta.")
                metadata = {
                    "agent_used": result.get("agent_used", "—"),
                    "tool_used":  result.get("tool_used"),
                    "sources":    result.get("sources", []),
                }
                st.markdown(response_text)
                st.session_state.messages.append(
                    {"role": "assistant", "content": response_text, "metadata": metadata}
                )

        # Expander fuera del chat_message para consistencia con el historial
        if result is not None and metadata is not None:
            _render_metadata_expander(metadata)


if __name__ == "__main__":
    main()
