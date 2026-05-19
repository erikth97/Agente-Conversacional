"""SQL Tool — consulta estructurada sobre procesos operativos en SQLite.

Responsabilidad única: dado un proceso_id, retorna los datos del registro
correspondiente en la tabla procesos_operativos. No interpreta ni sintetiza.
"""

import logging
import sqlite3
from pathlib import Path

from app import config

logger = logging.getLogger(__name__)


class SQLTool:
    """Consulta la tabla procesos_operativos en la base de datos SQLite.

    Solo retorna lo que existe en la BD. Si el proceso_id no existe,
    retorna un dict con clave 'error' — nunca inventa datos.
    """

    def __init__(self) -> None:
        self._db_path = Path(config.DB_PATH)

    def query(self, proceso_id: str) -> dict:
        """Retorna los datos del proceso operativo indicado.

        Args:
            proceso_id: Código del proceso ('A'–'E'). Se normaliza a mayúsculas.

        Returns:
            dict con los campos del registro si existe:
              proceso_id, nombre_proceso, area_responsable,
              tiempo_promedio_resolucion, canal_atencion, nivel_criticidad
            o dict con clave 'error' si el proceso_id no existe en la BD.
        """
        pid = proceso_id.strip().upper()

        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT * FROM procesos_operativos WHERE proceso_id = ?",
                    (pid,),
                ).fetchone()
        except Exception as e:
            logger.error(f"SQLTool query failed for proceso_id='{pid}': {e}")
            raise

        if row is None:
            logger.warning(f"SQLTool: proceso_id='{pid}' not found")
            return {"error": f"Proceso {pid} no encontrado en la base de datos operativa"}

        result = dict(row)
        logger.info(f"SQLTool: proceso_id='{pid}' found — nombre='{result['nombre_proceso']}'")
        return result
