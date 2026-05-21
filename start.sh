#!/bin/bash
set -e

echo "=== Banorte Agent — Container Startup ==="

echo "[1/3] Initializing database..."
python -c "from app.database.init_db import init; init()"

echo "[2/3] Running RAG ingestion pipeline..."
# El pipeline es idempotente (upsert por MD5) — re-ejecutar no duplica chunks.
# Con OPENAI_API_KEY=dummy (smoke test CI) la ingesta falla sin romper el arranque.
python scripts/ingest.py || echo "WARNING: ingestion skipped — server starts without RAG (expected in CI with dummy API key)"

echo "[3/3] Starting API server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
