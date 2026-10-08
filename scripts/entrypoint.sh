#!/bin/sh
set -e

# ==============================================================================
# Script de démarrage Personal Assistant Hub avec réplication Litestream
# ==============================================================================

DB_PATH="${SQLITE_DB_PATH:-/app/hub_data.db}"
REPLICA_URL="${LITESTREAM_REPLICA_URL:-}"
PORT="${PORT:-8000}"

# Configuration des credentials GCP pour Litestream si fournis en base64/JSON
if [ -n "$GOOGLE_SERVICE_ACCOUNT_INFO" ] && [ -z "$GOOGLE_APPLICATION_CREDENTIALS" ]; then
    CRED_FILE="/tmp/gcp_sa_credentials.json"
    if echo "$GOOGLE_SERVICE_ACCOUNT_INFO" | grep -q '^{'; then
        echo "$GOOGLE_SERVICE_ACCOUNT_INFO" > "$CRED_FILE"
    else
        echo "$GOOGLE_SERVICE_ACCOUNT_INFO" | base64 -d > "$CRED_FILE" 2>/dev/null || true
    fi
    if [ -s "$CRED_FILE" ]; then
        export GOOGLE_APPLICATION_CREDENTIALS="$CRED_FILE"
        echo "🔑 Credentials Google Cloud configurés pour Litestream."
    fi
fi

# Mode avec réplication continue Litestream vers Bucket Cloud (GCS, S3, R2)
if [ -n "$REPLICA_URL" ]; then
    echo "=================================================================="
    echo "🚀 Litestream activé : Réplication vers $REPLICA_URL"
    echo "=================================================================="

    # 1. Restauration initiale si la base locale n'existe pas encore
    if [ ! -f "$DB_PATH" ]; then
        echo "📥 Recherche d'une sauvegarde existante dans le bucket Cloud..."
        litestream restore -if-replica-exists -o "$DB_PATH" "$REPLICA_URL" || echo "ℹ️ Aucune sauvegarde précédente trouvée, création d'une nouvelle base."
    else
        echo "ℹ️ Base SQLite locale $DB_PATH déjà présente."
    fi

    # 2. Lancement du serveur Uvicorn enveloppé par le daemon de réplication Litestream
    echo "⚡ Démarrage du serveur Uvicorn avec synchronisation WAL continue..."
    exec litestream replicate -exec "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}" "$DB_PATH" "$REPLICA_URL"

else
    # Mode direct sans réplication (développement local ou sans bucket)
    echo "ℹ️ Aucune URL de réplication Litestream configurée (mode standard)."
    echo "⚡ Démarrage direct d'Uvicorn sur le port ${PORT}..."
    exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"
fi
