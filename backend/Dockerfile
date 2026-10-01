# KYRO backend image: FastAPI API + ingestion worker + sync supervisor.
# Build context is the repository root (see app/docker-compose.yml).
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /kyro

COPY backend/requirements.txt /kyro/requirements.txt
RUN pip install --no-cache-dir -r /kyro/requirements.txt

COPY backend/ /kyro/

# Default: API. The worker/sync services override `command` in compose.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
