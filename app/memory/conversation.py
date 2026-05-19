"""Memoria conversacional persistente por conversation_id.

Usa la tabla conversation_history en SQLite (creada en init_db.py).
Responsabilidad única: leer y escribir turnos de conversación.
No modifica, resume ni infiere contenido del historial almacenado.
"""

import logging
import sqlite3
from pathlib import Path

from app import config

logger = logging.getLogger(__name__)

# Máximo de turnos (user + assistant) a retornar en get_history.
# 20 turnos = 40 filas en SQLite (20 user + 20 assistant).
MAX_HISTORY: int = 20


class ConversationMemory:
    """Persiste y recupera el historial de conversación en SQLite.

    El historial está aislado por conversation_id — cada conversación
    es independiente y no interfiere con otras.
    """

    def __init__(self) -> None:
        self._db_path = Path(config.DB_PATH)

    def get_history(self, conversation_id: str) -> list[dict]:
        """Retorna los últimos MAX_HISTORY turnos de una conversación.

        Args:
            conversation_id: Identificador único de la conversación.

        Returns:
            Lista de dicts con 'role' y 'content', ordenada cronológicamente
            (más antiguo primero). Lista vacía si no hay historial.
        """
        # Traemos las últimas MAX_HISTORY*2 filas (cada turno = 2 filas)
        limit = MAX_HISTORY * 2
        try:
            with sqlite3.connect(self._db_path) as conn:
                rows = conn.execute(
                    """
                    SELECT role, content
                    FROM conversation_history
                    WHERE conversation_id = ?
                    ORDER BY id ASC
                    LIMIT ?
                    """,
                    (conversation_id, limit),
                ).fetchall()
        except Exception as e:
            logger.error(f"ConversationMemory.get_history failed for id='{conversation_id}': {e}")
            raise

        history = [{"role": role, "content": content} for role, content in rows]
        logger.info(f"ConversationMemory.get_history: conversation_id='{conversation_id}' messages={len(history)}")
        return history

    def add_turn(self, conversation_id: str, user_msg: str, assistant_msg: str) -> None:
        """Persiste un turno completo (user + assistant) en la base de datos.

        Args:
            conversation_id: Identificador único de la conversación.
            user_msg: Mensaje del usuario en este turno.
            assistant_msg: Respuesta del asistente en este turno.
        """
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.executemany(
                    """
                    INSERT INTO conversation_history (conversation_id, role, content)
                    VALUES (?, ?, ?)
                    """,
                    [
                        (conversation_id, "user", user_msg),
                        (conversation_id, "assistant", assistant_msg),
                    ],
                )
        except Exception as e:
            logger.error(f"ConversationMemory.add_turn failed for id='{conversation_id}': {e}")
            raise

        logger.info(f"ConversationMemory.add_turn: conversation_id='{conversation_id}' turn persisted")
