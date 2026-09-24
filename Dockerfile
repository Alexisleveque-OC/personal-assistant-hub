# ==============================================================================
# Dockerfile - Personal Assistant Hub (Production Cloud Ready)
# Compatible : Google Cloud Run, Render, Railway, Koyeb, Docker Compose
# ==============================================================================

FROM python:3.12-slim

# Variables d'environnement de base Python
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

# Création du répertoire applicatif
WORKDIR /app

# Installation des dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copie du code applicatif
COPY app/ ./app/
COPY scripts/ ./scripts/

# Création d'un utilisateur non-root pour des raisons de sécurité Cloud
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

# Exposition du port (valeur par défaut)
EXPOSE 8000

# Démarrage avec prise en charge dynamique du port Cloud Run / PaaS ($PORT)
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
