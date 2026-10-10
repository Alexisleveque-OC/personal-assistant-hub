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
        if ! litestream restore -if-replica-exists -o "$DB_PATH" "$REPLICA_URL"; then
            echo "⚠️ Échec de litestream restore avec GOOGLE_APPLICATION_CREDENTIALS."
            if [ -n "$GOOGLE_APPLICATION_CREDENTIALS" ]; then
                echo "🔄 Tentative de repli sur les identifiants Cloud Run natifs (ADC)..."
                OLD_GAC="$GOOGLE_APPLICATION_CREDENTIALS"
                unset GOOGLE_APPLICATION_CREDENTIALS
                if litestream restore -if-replica-exists -o "$DB_PATH" "$REPLICA_URL"; then
                    echo "✅ Restauration réussie avec les identifiants Cloud Run natifs !"
                else
                    echo "⚠️ Échec également avec les identifiants natifs. Rétablissement de GOOGLE_APPLICATION_CREDENTIALS."
                    export GOOGLE_APPLICATION_CREDENTIALS="$OLD_GAC"
                fi
            fi
        fi

        if [ -f "$DB_PATH" ]; then
            echo "✅ Base de données SQLite restaurée avec succès depuis le bucket Cloud !"
        else
            echo "ℹ️ Aucun réplica préexistant ou base introuvable. Initialisation d'une nouvelle base."
        fi
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
