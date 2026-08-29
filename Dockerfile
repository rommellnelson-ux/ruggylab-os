# syntax=docker/dockerfile:1
# ──────────────────────────────────────────────────────────────────────────────
# Stage 1 – builder : install Python deps in an isolated venv
# ──────────────────────────────────────────────────────────────────────────────
# Base ÉPINGLÉE par version exacte ET par digest. `3.13-slim` est un tag
# FLOTTANT : il suit les correctifs et change de contenu sans prévenir. Une
# release construite sur une base flottante n'est pas reproductible, et les
# preuves de conformité de ses composants GPL/LGPL ne décriraient plus
# l'image livrée. Voir docs/compliance/SOURCE_COMPLIANCE.md.
FROM python:3.13.15-slim-trixie@sha256:7ce4b6dfe35e55397b7cda544f8a13f191b7ae28dc5aad71fe664dbc9bc2623f AS builder

WORKDIR /app

# Build-time system deps (gcc needed by some C-ext wheels)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy only the dependency manifest first (layer-cache friendly)
COPY requirements.txt .

# Create venv and populate it
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ──────────────────────────────────────────────────────────────────────────────
# Stage 2 – runtime : minimal image, non-root user, no build tools
# ──────────────────────────────────────────────────────────────────────────────
FROM python:3.13.15-slim-trixie@sha256:7ce4b6dfe35e55397b7cda544f8a13f191b7ae28dc5aad71fe664dbc9bc2623f AS runtime

# OCI standard labels
LABEL org.opencontainers.image.title="RuggyLab OS" \
      org.opencontainers.image.description="Laboratory Information System for hospitals in Côte d'Ivoire" \
      org.opencontainers.image.source="https://github.com/rommellnelson-ux/ruggylab-os" \
      org.opencontainers.image.licenses="GPL-2.0" \
      org.opencontainers.image.vendor="RuggyLab"

WORKDIR /app

# Non-root user/group
RUN groupadd -r ruggylab && useradd -r -g ruggylab -s /sbin/nologin ruggylab

# Copy the pre-built venv from builder (no compiler needed at runtime)
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application source (owned by the non-root user)
COPY --chown=ruggylab:ruggylab app/       ./app/
COPY --chown=ruggylab:ruggylab alembic/   ./alembic/
COPY --chown=ruggylab:ruggylab alembic.ini .

# Runtime directories (must exist before USER switch).
# `logs` inclus par précaution : le défaut journalise sur stdout (LOG_FILE=None),
# mais un opérateur peut définir LOG_FILE=logs/app.log sans casser le non-root.
RUN mkdir -p data microscopy models backups logs && \
    chown -R ruggylab:ruggylab data microscopy models backups logs

# Drop privileges
USER ruggylab

# API port
EXPOSE 8000

# Liveness probe (used by Docker and docker-compose)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c \
        "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')" \
        || exit 1

# Default: run uvicorn directly (migrations handled by the dedicated `migrate`
# service in docker-compose, or run manually before deploying).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
