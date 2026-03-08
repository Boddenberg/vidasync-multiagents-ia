FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md /app/
COPY src /app/src
COPY knowledge /app/knowledge
COPY docs /app/docs

RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir .

EXPOSE 8000

CMD ["sh", "-c", "uvicorn vidasync_multiagents_ia.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
