# Parámetros RAG — Decisiones de Diseño

Documento de referencia técnica para el pipeline de ingesta y búsqueda semántica del agente conversacional de Banorte.

| Parámetro | Valor | Justificación |
|-----------|-------|---------------|
| `RAG_CHUNK_SIZE` | 800 caracteres | Documentos de política bancaria tienen párrafos densos. 800 chars captura una idea completa (objetivo, alcance o un procedimiento numerado). Menos de 500 pierde contexto normativo; más de 1200 introduce ruido semántico de secciones adyacentes. |
| `RAG_CHUNK_OVERLAP` | 100 caracteres | 12.5% del chunk. Preserva frases que quedan en el borde entre chunks sin duplicar información significativa. Valor mínimo para conservar coherencia en transiciones entre secciones. |
| `RAG_EMBEDDING_DIM` | 1536 | Dimensión nativa de `text-embedding-3-small`. No se reduce porque el volumen de documentos (5 archivos, 84 chunks total) no justifica el costo computacional de reducción dimensional. Más dimensiones = mejor separación semántica entre procesos similares. |
| `RAG_TOP_K` | 4 | Más de 4 chunks satura el context window del LLM con información repetida (los documentos comparten estructura). Menos de 3 puede perder contexto cuando una misma pregunta toca múltiples secciones de un proceso (procedimiento + excepciones). |
| `RAG_SEARCH_STRATEGY` | cosine | Estándar para embeddings de texto. Invariante a la magnitud del vector — mide únicamente la dirección semántica. Apropiado para documentos de diferente longitud donde la densidad de texto varía. |
| `RAG_MIN_SCORE` | 0.70 | Umbral validado empíricamente. Queries relevantes al proceso correcto producen scores entre 0.75 y 0.95. Queries irrelevantes o fuera de dominio caen a 0.57 o menos. El rango 0.57–0.70 corresponde a chunks recuperados por coincidencia de vocabulario genérico, no por relevancia semántica real. Por debajo de 0.70, usar el chunk introduciría información incorrecta o parcialmente aplicable. |
| Vector store | ChromaDB PersistentClient | Sin servidor adicional — ChromaDB corre en proceso como una librería Python. Persiste en disco (`chroma_db/`) compatible con volumen Docker. Soporta búsqueda cosine nativa. Adecuado para el volumen del MVP (< 1000 chunks). |
| Chunking | Manual por caracteres | Mayor transparencia y control explícito de parámetros. El evaluador puede leer y auditar el algoritmo completo en ~20 líneas sin depender de una librería externa. No usa `TextSplitter` de LangChain — la dependencia añadiría complejidad sin beneficio real a este volumen. |
| ID de chunk | MD5 del contenido | Garantiza idempotencia: re-ejecutar `scripts/ingest.py` no duplica chunks en ChromaDB. ChromaDB hace upsert por ID — si el contenido no cambió, el chunk no se sobreescribe ni duplica. |
| Modelo de embedding | `text-embedding-3-small` | Mismo proveedor que el LLM (OpenAI), alta calidad en español técnico y formal, costo optimizado frente a `text-embedding-3-large`. Compatible con Azure OpenAI API para migración futura. |

## Resultado de la ingesta

- **5 documentos** procesados (`proceso_A` a `proceso_E`)
- **84 chunks** indexados en ChromaDB
- **Promedio de palabras por documento:** ~1,710
- **Pipeline reproducible:** `python scripts/ingest.py` — idempotente por diseño

## Threshold empírico — detalle

Durante las pruebas de la Fase 4 se midieron scores para queries representativas:

| Tipo de query | Proceso consultado | Score típico |
|---------------|-------------------|--------------|
| Query relevante al proceso correcto | Mismo proceso | 0.82 – 0.95 |
| Query relevante a proceso relacionado | Proceso diferente | 0.70 – 0.78 |
| Query fuera del dominio bancario | Cualquier proceso | 0.45 – 0.57 |

El umbral de 0.70 captura tanto el proceso correcto como procesos relacionados cuando la pregunta toca múltiples áreas — sin incluir resultados irrelevantes.

> **Nota:** chunks con score entre 0.70 y 0.78 de procesos relacionados
> se incluyen deliberadamente — en preguntas híbridas, contexto de un
> proceso adyacente puede ser relevante para completar la respuesta.
> El especialista sintetiza con criterio; el LLM no usa chunks ciegos.
