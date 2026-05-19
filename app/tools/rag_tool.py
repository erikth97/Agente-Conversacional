"""RAG Tool — recuperación semántica sobre documentos de procesos operativos.

Usa ChromaDB como vector store y text-embedding-3-small para los embeddings.
Todos los parámetros vienen de app/config.py — ningún valor está hardcodeado.
"""

import logging

import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

from app import config

logger = logging.getLogger(__name__)


class RAGTool:
    """Recupera chunks relevantes de la base vectorial ChromaDB.

    Responsabilidad única: dado un query en lenguaje natural, retorna los
    chunks más similares junto con sus scores y los parámetros usados.
    No sintetiza ni interpreta — eso es responsabilidad del specialist_node.
    """

    def __init__(self) -> None:
        self._client = self._init_client()
        self._collection = self._get_collection()

    def _init_client(self) -> chromadb.PersistentClient:
        """Inicializa el cliente persistente de ChromaDB."""
        client = chromadb.PersistentClient(path=config.CHROMA_PATH)
        logger.info(f"ChromaDB client initialized at path='{config.CHROMA_PATH}'")
        return client

    def _get_collection(self) -> chromadb.Collection:
        """Obtiene la colección de ChromaDB con la función de embedding configurada."""
        embedding_fn = OpenAIEmbeddingFunction(
            api_key=config.OPENAI_API_KEY,
            model_name=config.EMBEDDING_MODEL,
        )
        collection = self._client.get_or_create_collection(
            name=config.CHROMA_COLLECTION,
            embedding_function=embedding_fn,
            metadata={"hnsw:space": config.RAG_SEARCH_STRATEGY},
        )
        logger.info(f"Collection '{config.CHROMA_COLLECTION}' ready — {collection.count()} chunks indexed")
        return collection

    def search(self, query: str) -> dict:
        """Busca los chunks más relevantes para el query dado.

        Args:
            query: Texto de la consulta en lenguaje natural.

        Returns:
            dict con:
              - chunks: list de dicts con keys 'content', 'source', 'score'
              - params: dict con los parámetros RAG usados en la búsqueda
              - query: el query original
        """
        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=min(config.RAG_TOP_K, self._collection.count() or 1),
                include=["documents", "metadatas", "distances"],
            )
        except Exception as e:
            logger.error(f"ChromaDB query failed for query='{query}': {e}")
            raise

        chunks = self._parse_results(results)
        top_score = chunks[0]["score"] if chunks else 0.0
        logger.info(
            f"RAG search: query='{query[:60]}' "
            f"chunks_returned={len(chunks)} "
            f"top_score={top_score:.3f}"
        )

        return {
            "query": query,
            "chunks": chunks,
            "params": {
                "chunk_size": config.RAG_CHUNK_SIZE,
                "overlap": config.RAG_CHUNK_OVERLAP,
                "embedding_dim": config.RAG_EMBEDDING_DIM,
                "top_k": config.RAG_TOP_K,
                "search_strategy": config.RAG_SEARCH_STRATEGY,
                "min_score": config.RAG_MIN_SCORE,
                "collection": config.CHROMA_COLLECTION,
            },
        }

    def _parse_results(self, results: dict) -> list[dict]:
        """Convierte el resultado crudo de ChromaDB a lista de chunks normalizados.

        ChromaDB retorna distancias (0 = idéntico). Para estrategia cosine,
        la similitud = 1 - distancia, lo que produce scores en [0, 1].
        """
        chunks: list[dict] = []

        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for doc, meta, dist in zip(documents, metadatas, distances):
            # Cosine distance en ChromaDB: 0 = perfecta similitud, 2 = opuestos.
            # Normalizamos a score de similitud en [0, 1].
            score = round(1 - (dist / 2), 4)
            chunks.append({
                "content": doc,
                "source": meta.get("source", "unknown"),
                "score": score,
            })

        return chunks
