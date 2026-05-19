"""Pipeline de ingesta RAG — carga documentos, genera chunks y los indexa en ChromaDB.

Flujo: archivos .txt en docs/ → chunking manual con overlap → embeddings → upsert ChromaDB.

Idempotente: el ID de cada chunk es el hash MD5 de su contenido.
Re-ejecutar no duplica chunks — ChromaDB hace upsert por ID.

Uso:
    python scripts/ingest.py
"""

import hashlib
import logging
import sys
from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

# Aseguramos que el directorio raíz del proyecto esté en el path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import config  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("ingest")

DOCS_DIR = Path(__file__).parent.parent / "docs"


def load_documents() -> list[dict]:
    """Carga todos los archivos .txt del directorio docs/.

    Returns:
        Lista de dicts con 'content' (texto completo) y 'source' (nombre del archivo sin extensión).
    """
    docs = []
    for path in sorted(DOCS_DIR.glob("*.txt")):
        content = path.read_text(encoding="utf-8")
        docs.append({"content": content, "source": path.stem})
        logger.info(f"Loaded: {path.name} ({len(content)} chars)")
    return docs


def chunk_document(content: str, source: str) -> list[dict]:
    """Divide un documento en chunks con overlap.

    Usa chunking manual por caracteres (no LangChain TextSplitter)
    para mayor transparencia y control explícito de los parámetros.

    Los parámetros chunk_size y overlap vienen de config.py.

    Args:
        content: Texto completo del documento.
        source: Nombre del documento (para metadata).

    Returns:
        Lista de dicts con 'content', 'source', 'chunk_index' e 'id'.
    """
    size = config.RAG_CHUNK_SIZE
    overlap = config.RAG_CHUNK_OVERLAP
    step = size - overlap

    chunks = []
    start = 0
    chunk_index = 0

    while start < len(content):
        end = start + size
        chunk_text = content[start:end].strip()

        if chunk_text:
            # ID determinístico = MD5 del contenido — garantiza idempotencia
            chunk_id = hashlib.md5(chunk_text.encode("utf-8")).hexdigest()
            chunks.append({
                "id": chunk_id,
                "content": chunk_text,
                "source": source,
                "chunk_index": chunk_index,
            })
            chunk_index += 1

        start += step

    return chunks


def get_collection() -> chromadb.Collection:
    """Inicializa ChromaDB y retorna la colección configurada."""
    client = chromadb.PersistentClient(path=config.CHROMA_PATH)
    embedding_fn = OpenAIEmbeddingFunction(
        api_key=config.OPENAI_API_KEY,
        model_name=config.EMBEDDING_MODEL,
    )
    collection = client.get_or_create_collection(
        name=config.CHROMA_COLLECTION,
        embedding_function=embedding_fn,
        metadata={"hnsw:space": config.RAG_SEARCH_STRATEGY},
    )
    return collection


def ingest() -> None:
    """Ejecuta el pipeline completo de ingesta.

    1. Carga documentos .txt desde docs/
    2. Genera chunks con overlap
    3. Hace upsert en ChromaDB (idempotente por ID MD5)
    """
    logger.info("=== Iniciando pipeline de ingesta RAG ===")
    logger.info(
        f"Params: chunk_size={config.RAG_CHUNK_SIZE} "
        f"overlap={config.RAG_CHUNK_OVERLAP} "
        f"embedding={config.EMBEDDING_MODEL} "
        f"dim={config.RAG_EMBEDDING_DIM} "
        f"collection={config.CHROMA_COLLECTION}"
    )

    documents = load_documents()
    if not documents:
        logger.error(f"No se encontraron archivos .txt en {DOCS_DIR}")
        sys.exit(1)

    collection = get_collection()

    total_chunks = 0
    for doc in documents:
        chunks = chunk_document(doc["content"], doc["source"])
        if not chunks:
            continue

        collection.upsert(
            ids=[c["id"] for c in chunks],
            documents=[c["content"] for c in chunks],
            metadatas=[
                {"source": c["source"], "chunk_index": c["chunk_index"]}
                for c in chunks
            ],
        )
        logger.info(f"Upserted: {doc['source']} → {len(chunks)} chunks")
        total_chunks += len(chunks)

    final_count = collection.count()
    logger.info(f"=== Ingesta completa: {total_chunks} chunks procesados, {final_count} en coleccion ===")


if __name__ == "__main__":
    ingest()
