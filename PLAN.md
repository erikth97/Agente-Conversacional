# Plan de Desarrollo — Banorte Agente Conversacional
# Evaluador: Pavel Palma Nicolás, Banorte
# Este archivo es el mapa de construcción fase por fase.
# Actualizar el checkbox [ ] -> [x] al completar cada fase.

## Grafo de Dependencias

FASE 1 (Fundación)
    │
    ├──► FASE 2 (BD SQLite)          ← paralelo con FASE 3
    │
    └──► FASE 3 (Documentos RAG)     ← paralelo con FASE 2
              │
              ▼
         FASE 4 (RAG Tool + ingest.py)    ← requiere FASE 1 + FASE 3
              │
              ├──► FASE 5 (SQL Tool)      ← paralelo con FASE 6, requiere FASE 2
              │
              └──► FASE 6 (Memoria)       ← paralelo con FASE 5, requiere FASE 2
                        │
              ┌─────────┘
              ▼
         FASE 7 (LangGraph)               ← requiere FASE 4 + 5 + 6
              │
              ▼
         FASE 8 (FastAPI)                 ← requiere FASE 7
              │
              ▼
         FASE 9 (README)                  ← requiere FASE 8
              │
              ▼
         FASE 10 (Docker + CI/CD)         ← requiere FASE 9
              │
              ▼
         FASE 11 (Streamlit)              ← solo si FASE 1-10 al 100%


## Checklist por Fase

### [x] FASE 1 — Fundación
Archivos creados:
- requirements.txt
- app/config.py          — centraliza os.getenv(), valida OPENAI_API_KEY al importar
- .env.example           — template con todas las variables comentadas
- .gitignore             — excluye .env, CLAUDE.md, banorte.db, chroma_db/, etc.
- app/__init__.py
- app/graph/__init__.py
- app/tools/__init__.py
- app/memory/__init__.py
- app/database/__init__.py

Verificación OK:
  - Sin OPENAI_API_KEY → ValueError claro ✅
  - Con OPENAI_API_KEY → Config OK: gpt-4o-mini ✅

---

### [ ] FASE 2 — Base de Datos SQLite
Archivos a crear:
- app/database/init_db.py

Función init() idempotente con:
- CREATE TABLE IF NOT EXISTS procesos_operativos (proceso_id, nombre_proceso,
  area_responsable, tiempo_promedio_resolucion, canal_atencion, nivel_criticidad)
- CREATE TABLE IF NOT EXISTS conversation_history (id, conversation_id, role,
  content, timestamp)
- CREATE INDEX IF NOT EXISTS idx_conv_id ON conversation_history(conversation_id)
- Seed data: 5 procesos A-E

Verificación:
  python -c "from app.database.init_db import init; init()"
  sqlite3 app/database/banorte.db "SELECT proceso_id, nombre_proceso FROM procesos_operativos;"

---

### [ ] FASE 3 — Documentos RAG (5 archivos .txt)
Archivos a crear (500+ palabras c/u, texto plano, lenguaje de política bancaria):
- docs/proceso_A_aclaraciones.txt
- docs/proceso_B_cancelaciones.txt
- docs/proceso_C_escalamiento.txt
- docs/proceso_D_actualizacion.txt
- docs/proceso_E_quejas.txt

Estructura de cada documento:
  POLÍTICA OPERATIVA INTERNA — [NOMBRE]
  Código: [A|B|C|D|E] | Versión: 1.0
  1. OBJETIVO
  2. ALCANCE
  3. MARCO NORMATIVO (CNBV, CONDUSEF, Circular aplicable)
  4. DEFINICIONES
  5. PROCEDIMIENTO (pasos numerados)
  6. TIEMPOS DE RESOLUCIÓN
  7. ÁREA RESPONSABLE Y ROLES
  8. CANALES DE ATENCIÓN
  9. EXCEPCIONES
  10. DISPOSICIONES FINALES

Verificación:
  wc -w docs/*.txt   # cada archivo debe mostrar 500+ palabras

---

### [ ] FASE 4 — RAG Tool + Pipeline de Ingesta
Archivos a crear:
- app/tools/rag_tool.py    — clase RAGTool con search(query: str) -> dict
- scripts/ingest.py        — ETL: carga .txt → chunking → embeddings → ChromaDB

Detalles:
- Chunking manual (no LangChain TextSplitter) — más legible
- ID de chunk = hash MD5 del contenido (idempotencia)
- Parámetros desde config.py: chunk_size, overlap, top_k, embedding_dim
- search() retorna params con valores usados (transparencia)

Verificación:
  python scripts/ingest.py
  python -c "from app.tools.rag_tool import RAGTool; r = RAGTool(); result = r.search('proceso de aclaraciones'); print(result)"

---

### [ ] FASE 5 — SQL Tool
Archivo a crear:
- app/tools/sql_tool.py    — clase SQLTool con query(proceso_id: str) -> dict

Verificación:
  python -c "from app.tools.sql_tool import SQLTool; s = SQLTool(); print(s.query('A')); print(s.query('Z'))"

---

### [ ] FASE 6 — Memoria Conversacional
Archivo a crear:
- app/memory/conversation.py   — clase ConversationMemory con get_history() y add_turn()

SQLite persistente por conversation_id.

Verificación:
  python -c "
  from app.memory.conversation import ConversationMemory
  m = ConversationMemory()
  m.add_turn('conv-test', 'Hola', 'Hola, soy el asistente')
  history = m.get_history('conv-test')
  assert len(history) == 2
  print('Memoria OK — turnos:', len(history))
  "

---

### [ ] FASE 7 — Agentes LangGraph
Archivos a crear:
- app/graph/state.py             — AgentState TypedDict
- app/graph/orchestrator_node.py — clasifica intent, NO hace RAG ni SQL
- app/graph/specialist_node.py   — tool calling híbrido, max 4 iteraciones
- app/graph/graph.py             — StateGraph con nodos, edges, compile()

AgentState:
  conversation_id, user_id, user_message, messages (Annotated+add_messages),
  intent ('operativo'|'general'), response, agent_used, tool_used, sources

Flujo:
  START → orchestrator_node
    intent='general'   → responde directo → END
    intent='operativo' → specialist_node → END

Verificación:
  python -c "from app.graph.graph import agent_graph; result = agent_graph.invoke({...}); print(result['agent_used'], result['tool_used'])"

---

### [ ] FASE 8 — FastAPI
Archivo a crear:
- app/main.py   — POST /chat, GET /health, GET /conversations/{id}

Body exacto del assessment (ver CLAUDE.md sección 8).
Verificación con curls (ver CLAUDE.md sección FASE 8).

---

### [ ] FASE 9 — README
Archivo a crear:
- README.md

Secciones obligatorias:
- Descripción, Arquitectura (ASCII), Requisitos previos
- Instalación local, Ejecución local, Ejecución Docker
- Ejemplos de uso (curls con output esperado)
- Tabla de decisiones de diseño RAG (parámetros + justificación)
- Estructura del proyecto, Criterios de evaluación cubiertos, CI/CD

---

### [ ] FASE 10 — Docker + CI/CD
Archivos a crear:
- Dockerfile            — Python 3.12-slim, expone 8000
- start.sh              — init_db → ingest → uvicorn (chmod +x)
- docker-compose.yml    — volumen chroma_db, env_file
- .github/workflows/ci.yml  — ruff lint + docker build + smoke test /health

Verificación:
  docker build -t banorte-agent .
  docker run --env-file .env -p 8000:8000 banorte-agent
  curl http://localhost:8000/health

---

### [ ] FASE 11 — Streamlit Frontend (valor agregado)
SOLO ejecutar si FASE 1-10 están al 100% verificadas.

Archivo a crear:
- frontend/app.py   — chat UI, muestra response + agent_used + tool_used + sources


## Ponderación del Assessment

| Componente              | Peso  | Estado |
|-------------------------|-------|--------|
| Arquitectura agéntica   | 20%   | [ ]    |
| Agente Orquestador      | 20%   | [ ]    |
| Agente Especializado    | 20%   | [ ]    |
| RAG custom              | 20%   | [ ]    |
| BD Estructurada         | 10%   | [ ]    |
| Memoria Conversacional  | 10%   | [ ]    |
| Dockerfile funcional    | +10%  | [ ]    |
| Config por env vars     | +5%   | [ ]    |
| README claro            | +5%   | [ ]    |
| **TOTAL POSIBLE**       | 120%  |        |


## Entregables Finales

1. Repositorio Git con acceso a:
   - pavel.palma.nicolas@banorte.com
   - pavel.palm.ni@gmail.com
2. .zip con código + documentos .txt
3. Demo en vivo por Microsoft Teams

## Reglas que no se negocian

- Cero credenciales en código fuente
- Toda config desde app/config.py via .env
- Una clase = una responsabilidad
- Sin magic numbers en código
- Logging con módulo logging, nunca print()
- ruff check app/ sin errores antes de cada commit
