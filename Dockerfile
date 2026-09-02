# syntax=docker/dockerfile:1
# ──────────────────────────────────────────────────────────────────────────────
# Stage 1 – builder : install Python deps in an isolated venv
# ──────────────────────────────────────────────────────────────────────────────
FROM python:3.13-slim AS builder

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
FROM python:3.13-slim AS runtime

# OCI standard labels
LABEL org.opencontainers.image.title="RuggyLab OS" \
      org.opencontainers.image.description="Laboratory Information System for hospitals in Côte d'Ivoire" \
      org.opencontainers.image.source="https://github.com/rommellnelson-ux/ruggylab-os" \
      org.opencontainers.image.licenses="LicenseRef-RuggyLab-Evaluation-1.0" \
      org.opencontainers.image.authors="WOGNIN Nelson Rommell Boni Ruggairrhye" \
      org.opencontainers.image.version="0.8.0-beta.1" \
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

# Licence et notices tierces embarquées dans l'image : une image distribuée sans
# ses conditions d'usage ni les notices de ses composants est incomplète, et
# plusieurs licences tierces l'exigent explicitement. Mode 0444 — lecture seule,
# y compris pour le propriétaire : ces fichiers ne doivent jamais être réécrits
# depuis le conteneur.
COPY --chown=ruggylab:ruggylab --chmod=0444 LICENSE.md              ./LICENSE.md
COPY --chown=ruggylab:ruggylab --chmod=0444 THIRD_PARTY_NOTICES.md  ./THIRD_PARTY_NOTICES.md
COPY --chown=ruggylab:ruggylab              licenses/third-party/   ./licenses/third-party/

# `--chmod` applique un mode UNIQUE à tout ce qu'il copie : sur une arborescence,
# 0444 retire le bit d'exécution des RÉPERTOIRES, qui deviennent intraversables.
# Les textes de licence seraient présents mais illisibles pour l'utilisateur du
# conteneur — une notice qu'on ne peut pas lire ne vaut pas notice. Le mode est
# donc posé par type : 0555 sur les répertoires, 0444 sur les fichiers.
RUN find ./licenses -type d -exec chmod 0555 {} + \
    && find ./licenses -type f -exec chmod 0444 {} +

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
