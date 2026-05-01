# ═══════════════════════════════════════════════════════════════
# SmartDacha Backend — Multi-stage Dockerfile (Refactored)
#
# FIXES from Code Review:
#   §4.4 — Dynamic Gunicorn workers via WEB_CONCURRENCY env var
#   §1.1 — No UI/Flet code (separate frontend repo)
# ═══════════════════════════════════════════════════════════════

# ─── Stage 1: Builder ─────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ─── Stage 2: Runtime ─────────────────────────────────────────
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r appuser && useradd -r -g appuser appuser

COPY --from=builder /opt/venv /opt/venv
RUN chown -R appuser:appuser /opt/venv

COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# §4.4 FIX: dynamic workers via env var (default=2)
# Formula recommendation: WEB_CONCURRENCY = 2 * CPU_CORES + 1
CMD ["sh", "-c", "gunicorn app.main:app \
    -w ${WEB_CONCURRENCY:-2} \
    -k uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8000 \
    --graceful-timeout 30 \
    --timeout 60 \
    --access-logfile - \
    --error-logfile -"]


# ─── Stage 3: Test image ──────────────────────────────────────────────────────
FROM runtime AS test

USER root
COPY requirements.txt /tmp/requirements.txt
COPY requirements-dev.txt /tmp/requirements-dev.txt
RUN pip install --no-cache-dir -r /tmp/requirements-dev.txt
RUN chown -R appuser:appuser /app

USER appuser
COPY --chown=appuser:appuser pytest.ini ./pytest.ini
COPY --chown=appuser:appuser tests ./tests

CMD ["pytest", "-q"]
