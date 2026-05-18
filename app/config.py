"""Centraliza toda la configuración del sistema.

Lee exclusivamente desde variables de entorno (archivo .env en desarrollo,
variables del sistema en Docker/producción).

REGLA: nunca importar os.getenv() fuera de este módulo.
"""

import os

from dotenv import load_dotenv

load_dotenv()

# ─── LLM y Embeddings ─────────────────────────────────────────────────────────
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

# ─── Parámetros RAG ───────────────────────────────────────────────────────────
RAG_CHUNK_SIZE: int = int(os.getenv("RAG_CHUNK_SIZE", "800"))
RAG_CHUNK_OVERLAP: int = int(os.getenv("RAG_CHUNK_OVERLAP", "100"))
RAG_EMBEDDING_DIM: int = int(os.getenv("RAG_EMBEDDING_DIM", "1536"))
RAG_TOP_K: int = int(os.getenv("RAG_TOP_K", "4"))
RAG_SEARCH_STRATEGY: str = os.getenv("RAG_SEARCH_STRATEGY", "cosine")

# ─── ChromaDB ────────────────────────────────────────────────────────────────
CHROMA_PATH: str = os.getenv("CHROMA_PATH", "./chroma_db")
CHROMA_COLLECTION: str = os.getenv("CHROMA_COLLECTION", "banorte_procesos")

# ─── Base de datos SQLite ─────────────────────────────────────────────────────
DB_PATH: str = os.getenv("DB_PATH", "./app/database/banorte.db")

# ─── Servidor ────────────────────────────────────────────────────────────────
HOST: str = os.getenv("HOST", "0.0.0.0")
PORT: int = int(os.getenv("PORT", "8000"))

# ─── Validación de inicio — falla rápido si falta configuración crítica ───────
if not OPENAI_API_KEY:
    raise ValueError(
        "OPENAI_API_KEY no configurada. "
        "Copia .env.example a .env y agrega tu API key de OpenAI."
    )
