"""Outil d'export et de sauvegarde des données sportives SQLite vers JSON et CSV.

Usage en ligne de commande :
    python scripts/export_sport_data.py [--output-dir backups/] [--format json|csv|all] [--db-path hub_data.db]
"""
import argparse
import csv
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

# Garantit que la racine du projet est dans sys.path lors de l'exécution en CLI
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import DatabaseManager, get_database_manager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def export_sport_data(
    db_manager: DatabaseManager,
    export_dir: str = "backups",
    export_format: str = "all",
) -> Dict[str, str]:
    """Exporte les données sportives (séances et synthèses) vers JSON et/ou CSV."""
    os.makedirs(export_dir, exist_ok=True)
    now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    created_files: Dict[str, str] = {}

    sessions = db_manager.get_sport_sessions()
    summaries = db_manager.get_all_sport_weekly_summaries()

    fmt = export_format.lower().strip()

    # 1. Export JSON
    if fmt in ("json", "all"):
        json_filename = f"sport_backup_{now_str}.json"
        json_filepath = os.path.join(export_dir, json_filename)
        payload = {
            "exported_at": datetime.now().isoformat(),
            "sessions_count": len(sessions),
            "summaries_count": len(summaries),
            "sessions": sessions,
            "summaries": summaries,
        }
        with open(json_filepath, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        created_files["json"] = json_filepath
        logger.info(f"Export JSON généré avec succès : {json_filepath}")

    # 2. Export CSV
    if fmt in ("csv", "all"):
        # CSV Séances
        sessions_filename = f"sport_sessions_{now_str}.csv"
        sessions_filepath = os.path.join(export_dir, sessions_filename)
        if sessions:
            fieldnames = list(sessions[0].keys())
        else:
            fieldnames = [
                "id", "date", "semaine", "statut", "type_seance", "distance_km",
                "denivele_d_plus", "duree_secondes", "ressenti_rpe", "fc_moyenne",
                "fc_max", "meteo_note", "programme", "remarques", "notes",
                "allure_cible", "vitesse_cible", "strava_id", "created_at", "updated_at"
            ]

        with open(sessions_filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in sessions:
                writer.writerow(row)
        created_files["sessions_csv"] = sessions_filepath
        logger.info(f"Export CSV Séances généré avec succès : {sessions_filepath}")

        # CSV Synthèses
        summaries_filename = f"sport_weekly_summaries_{now_str}.csv"
        summaries_filepath = os.path.join(export_dir, summaries_filename)
        if summaries:
            sum_fieldnames = list(summaries[0].keys())
        else:
            sum_fieldnames = [
                "id", "semaine", "annee", "nb_seances", "km_total", "d_plus_total",
                "km_effort_total", "duree_secondes", "charge_rpe_totale", "nb_renfo",
                "previous_week_km_effort", "vitesse_moyenne_kmh", "previous_week_vitesse_kmh",
                "previous_week_charge_rpe", "duree_course_secondes", "created_at", "updated_at"
            ]

        with open(summaries_filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=sum_fieldnames)
            writer.writeheader()
            for row in summaries:
                writer.writerow(row)
        created_files["summaries_csv"] = summaries_filepath
        logger.info(f"Export CSV Synthèses généré avec succès : {summaries_filepath}")

    return created_files


def main() -> None:
    """Point d'entrée CLI pour exécuter l'export de secours."""
    parser = argparse.ArgumentParser(description="Export et sauvegarde des données sportives SQLite vers JSON/CSV.")
    parser.add_argument("--output-dir", default="backups", help="Dossier de destination (défaut: backups/)")
    parser.add_argument("--format", choices=["json", "csv", "all"], default="all", help="Format de sortie (défaut: all)")
    parser.add_argument("--db-path", default=None, help="Chemin du fichier SQLite (défaut: hub_data.db)")
    args = parser.parse_args()

    db = DatabaseManager(db_path=args.db_path) if args.db_path else get_database_manager()
    db.init_db()

    logger.info(f"Démarrage de l'export des données sportives depuis {db.db_path} vers {args.output_dir}...")
    files = export_sport_data(db, export_dir=args.output_dir, export_format=args.format)

    logger.info("=== Fichiers d'export créés ===")
    for k, p in files.items():
        logger.info(f"- [{k}] {p}")


if __name__ == "__main__":
    main()
