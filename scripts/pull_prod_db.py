"""Outil de rapatriement de la base de données SQLite de production (Cloud Storage -> Local).

Usage en ligne de commande :
    python scripts/pull_prod_db.py [--replica-url gcs://bucket/hub_data.db] [--output hub_data.db] [--no-backup]
"""
import argparse
import base64
import logging
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from typing import Any, Dict, Optional

# Garantit que la racine du projet est dans sys.path lors de l'exécution en CLI
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def get_database_summary(db_path: str) -> Dict[str, int]:
    """Retourne le comptage des lignes des principales tables SQLite de la base."""
    if not os.path.exists(db_path):
        return {}

    summary: Dict[str, int] = {}
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        tables = [row[0] for row in cursor.fetchall()]

        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM \"{table}\";")
            summary[table] = cursor.fetchone()[0]
        conn.close()
    except Exception as exc:
        logger.warning(f"Impossible de lire le résumé de la base {db_path} : {exc}")
    return summary


def run_litestream_restore(
    replica_url: str,
    output_path: str,
    credentials_path: Optional[str] = None,
) -> bool:
    """Restaure un snapshot SQLite depuis le réplica Cloud (GCS/S3) via le binaire Litestream ou Docker."""
    abs_output = os.path.abspath(output_path)
    output_dir = os.path.dirname(abs_output) or os.getcwd()
    db_filename = os.path.basename(abs_output)

    # Préparation des credentials GCP
    cred_file = None
    configured_cred = getattr(settings, "google_service_account_file", None)
    candidate_paths = [
        credentials_path,
        configured_cred,
        "credentials/service_account.json",
        "credentials.json",
        os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"),
    ]

    for p in candidate_paths:
        if p and os.path.exists(p):
            cred_file = os.path.abspath(p)
            break

    if not cred_file and getattr(settings, "google_service_account_info", None):
        tmp_cred = Path("/tmp/gcp_sa_credentials_pull.json")
        info = settings.google_service_account_info.strip()
        if info.startswith("{"):
            tmp_cred.write_text(info, encoding="utf-8")
        else:
            try:
                decoded = base64.b64decode(info).decode("utf-8")
                tmp_cred.write_text(decoded, encoding="utf-8")
            except Exception:
                pass
        if tmp_cred.exists() and tmp_cred.stat().st_size > 0:
            cred_file = str(tmp_cred)

    # 1. Tentative avec le binaire local si installé
    tmp_filename = f"{db_filename}.restore_tmp"
    abs_tmp_output = os.path.join(output_dir, tmp_filename)
    if os.path.exists(abs_tmp_output):
        try:
            os.remove(abs_tmp_output)
        except OSError:
            pass

    success = False
    if shutil.which("litestream"):
        env = os.environ.copy()
        if cred_file:
            env["GOOGLE_APPLICATION_CREDENTIALS"] = cred_file
        cmd = ["litestream", "restore", "-o", abs_tmp_output, replica_url]
        logger.info(f"Exécution locale de Litestream : {' '.join(cmd)}")
        res = subprocess.run(cmd, env=env)
        success = (res.returncode == 0)
    elif shutil.which("docker"):
        # 2. Repli via Docker litestream/litestream:0.3.13
        docker_cmd = [
            "docker", "run", "--rm",
        ]
        if hasattr(os, "getuid") and hasattr(os, "getgid"):
            docker_cmd.extend(["--user", f"{os.getuid()}:{os.getgid()}"])
        docker_cmd.extend([
            "-v", f"{output_dir}:/data",
        ])
        if cred_file and os.path.exists(cred_file):
            cred_dir = os.path.dirname(cred_file)
            cred_name = os.path.basename(cred_file)
            docker_cmd.extend([
                "-v", f"{cred_dir}:/creds",
                "-e", f"GOOGLE_APPLICATION_CREDENTIALS=/creds/{cred_name}",
            ])

        docker_cmd.extend([
            "litestream/litestream:0.3.13",
            "restore",
            "-o", f"/data/{tmp_filename}",
            replica_url,
        ])
        logger.info(f"Exécution Docker de Litestream : {' '.join(docker_cmd)}")
        res = subprocess.run(docker_cmd)
        success = (res.returncode == 0)
    else:
        logger.error("Ni 'litestream' ni 'docker' ne sont installés sur votre machine hôte pour effectuer la restauration.")
        return False

    if success and os.path.exists(abs_tmp_output):
        os.replace(abs_tmp_output, abs_output)
        try:
            os.chmod(abs_output, 0o664)
        except OSError:
            pass

        # Nettoyage d'éventuels fichiers temporaires résiduels (ex: .tmp-shm / .tmp-wal)
        for residual in Path(output_dir).glob(f"{db_filename}.restore_tmp*"):
            try:
                residual.unlink()
            except OSError:
                pass
        return True

    # Nettoyage en cas d'échec
    for residual in Path(output_dir).glob(f"{db_filename}.restore_tmp*"):
        try:
            residual.unlink()
        except OSError:
            pass
    return False



def pull_production_database(
    replica_url: Optional[str] = None,
    output_path: str = "hub_data.db",
    make_backup: bool = True,
    credentials_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Rapatrie la base de production dans le fichier cible avec sauvegarde automatique."""
    target_url = (
        replica_url
        or getattr(settings, "litestream_replica_url", None)
        or os.environ.get("LITESTREAM_REPLICA_URL")
    )

    if not target_url:
        err = (
            "Aucune URL de réplication fournie.\n"
            "Spécifiez --replica-url gcs://votre-bucket/hub_data.db "
            "ou configurez LITESTREAM_REPLICA_URL dans votre fichier .env."
        )
        logger.error(err)
        return {"success": False, "error": err}

    # Sauvegarde de sécurité locale si le fichier existe déjà
    if make_backup and os.path.exists(output_path):
        backup_path = f"{output_path}.bak"
        logger.info(f"Création d'une sauvegarde locale préventive : {backup_path}")
        shutil.copy2(output_path, backup_path)

    logger.info(f"📥 Téléchargement du snapshot de production depuis {target_url} vers {output_path}...")
    success = run_litestream_restore(target_url, output_path, credentials_path=credentials_path)

    if not success:
        return {"success": False, "error": "Échec de la commande de restauration Litestream."}

    summary = get_database_summary(output_path)
    return {
        "success": True,
        "output_path": output_path,
        "summary": summary,
    }


def main() -> None:
    """Point d'entrée CLI."""
    parser = argparse.ArgumentParser(
        description="Rapatrie la base de données SQLite de production vers votre machine locale."
    )
    parser.add_argument(
        "--replica-url",
        default=None,
        help="URL du réplica Cloud (ex: gcs://nom-du-bucket/hub_data.db). Défaut: variable LITESTREAM_REPLICA_URL",
    )
    parser.add_argument(
        "--output",
        default="hub_data.db",
        help="Chemin du fichier SQLite local de destination (défaut: hub_data.db)",
    )
    parser.add_argument(
        "--credentials",
        default=None,
        help="Chemin du fichier JSON de compte de service GCP (défaut: credentials/service_account.json)",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Désactive la copie de sauvegarde .bak du fichier local existant",
    )
    args = parser.parse_args()

    result = pull_production_database(
        replica_url=args.replica_url,
        output_path=args.output,
        make_backup=not args.no_backup,
        credentials_path=args.credentials,
    )

    if result["success"]:
        print("\n========================================================")
        print("✅ Base de production rapatriée avec succès !")
        print(f"📁 Fichier local : {result['output_path']}")
        print("📊 Contenu des tables :")
        for table, count in result.get("summary", {}).items():
            print(f"   - {table} : {count} enregistrement(s)")
        print("========================================================\n")
    else:
        print(f"\n❌ Erreur : {result.get('error')}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
