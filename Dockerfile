FROM python:3.12-slim

WORKDIR /app

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# System dependencies required by ChromaDB and onnxruntime
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    --fix-missing \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies before copying source code —
# this layer is cached by Docker and only rebuilds when requirements.txt changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application source
COPY app/ ./app/
COPY scripts/ ./scripts/
COPY docs/ ./docs/

COPY start.sh .
RUN chmod +x start.sh

EXPOSE 8000

CMD ["./start.sh"]