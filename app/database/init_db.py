"""Inicialización idempotente de la base de datos SQLite.

Crea el schema y carga el seed data de procesos operativos.
Se puede ejecutar múltiples veces sin duplicar datos (INSERT OR IGNORE).
"""

import logging
import sqlite3
from pathlib import Path

from app import config

logger = logging.getLogger(__name__)

_SEED_DATA: list[tuple[str, str, str, str, str, str]] = [
    (
        "A",
        "Atención de Aclaraciones",
        "Operaciones y Calidad",
        "3-5 días hábiles",
        "Sucursal / Banca en línea",
        "Alto",
    ),
    (
        "B",
        "Cancelación de Productos",
        "Retención de Clientes",
        "1-2 días hábiles",
        "Sucursal / Teléfono / Digital",
        "Medio",
    ),
    (
        "C",
        "Escalamiento de Incidencias",
        "Mesa de Control Interno",
        "24 horas",
        "Interno (entre áreas)",
        "Crítico",
    ),
    (
        "D",
        "Actualización de Datos del Cliente",
        "Cumplimiento y KYC",
        "Inmediato - 2 días",
        "Sucursal / App",
        "Alto",
    ),
    (
        "E",
        "Gestión de Quejas Internas",
        "Contraloría Interna",
        "5-7 días hábiles",
        "Interno / Correo",
        "Medio",
    ),
]


class DatabaseInitializer:
    """Crea el schema y carga el seed data de la base de datos SQLite.

    Idempotente: ejecutar init() múltiples veces produce el mismo estado final.
    Usa CREATE TABLE IF NOT EXISTS e INSERT OR IGNORE para garantizarlo.
    """

    def __init__(self) -> None:
        self._db_path = Path(config.DB_PATH)

    def init(self) -> None:
        """Inicializa la base de datos: crea tablas, índice y seed data."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            self._create_tables(conn)
            self._seed_data(conn)
        logger.info(f"Database ready at {self._db_path}")

    def _create_tables(self, conn: sqlite3.Connection) -> None:
        """Crea las tablas y el índice si no existen."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS procesos_operativos (
                proceso_id                  TEXT PRIMARY KEY,
                nombre_proceso              TEXT NOT NULL,
                area_responsable            TEXT NOT NULL,
                tiempo_promedio_resolucion  TEXT NOT NULL,
                canal_atencion              TEXT NOT NULL,
                nivel_criticidad            TEXT NOT NULL
            )
        """)
        logger.info("Table 'procesos_operativos' ready")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversation_history (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT    NOT NULL,
                role            TEXT    NOT NULL,
                content         TEXT    NOT NULL,
                timestamp       TEXT    NOT NULL DEFAULT (datetime('now'))
            )
        """)
        logger.info("Table 'conversation_history' ready")

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_conv_id
                ON conversation_history(conversation_id)
        """)
        logger.info("Index 'idx_conv_id' ready")

    def _seed_data(self, conn: sqlite3.Connection) -> None:
        """Inserta los 5 procesos operativos. Ignora duplicados."""
        conn.executemany(
            """
            INSERT OR IGNORE INTO procesos_operativos
                (proceso_id, nombre_proceso, area_responsable,
                 tiempo_promedio_resolucion, canal_atencion, nivel_criticidad)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            _SEED_DATA,
        )
        inserted = conn.execute(
            "SELECT COUNT(*) FROM procesos_operativos"
        ).fetchone()[0]
        logger.info(f"Seed data: {inserted} procesos loaded")


def init() -> None:
    """Punto de entrada público para inicializar la base de datos."""
    DatabaseInitializer().init()
