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

# Copie du binaire statique officiel Litestream (multi-stage build léger, zéro dépendance)
COPY --from=litestream/litestream:0.3.13 /usr/local/bin/litestream /usr/local/bin/litestream

# Copie du code applicatif et scripts
COPY app/ ./app/
COPY scripts/ ./scripts/

# Rendre les scripts exécutables et assigner les droits à l'utilisateur non-root
RUN chmod +x /app/scripts/*.sh 2>/dev/null || true && \
    useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

# Exposition du port (valeur par défaut)
EXPOSE 8000

# Démarrage via le script d'entrée (gérant Uvicorn et la réplication optionnelle Litestream)
CMD ["/app/scripts/entrypoint.sh"]

