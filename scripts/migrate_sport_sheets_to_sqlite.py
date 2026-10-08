"""Script one-off d'aspiration et de migration des données sportives Google Sheets vers SQLite.

Usage en ligne de commande :
    python scripts/migrate_sport_sheets_to_sqlite.py [--db-path hub_data.db] [--dry-run]
"""
import argparse
from datetime import date
import logging
import sys
from typing import Any, Dict, List, Optional

from app.core.database import DatabaseManager, get_database_manager
from app.connectors.sheets.sport_connector import SportConnector
from app.connectors.sheets.sport_models import (
    SportSession,
    SportWeeklySummary,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def migrate_sheets_to_sqlite(
    sport_connector: Any,
    db_manager: DatabaseManager,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Aspire l'ensemble des séances et synthèses depuis Google Sheets vers SQLite de façon idempotente."""
    report: Dict[str, Any] = {
        "sessions_migrated": 0,
        "summaries_migrated": 0,
        "errors": [],
    }

    # 1. Migration des séances d'entraînement
    try:
        sessions: List[SportSession] = sport_connector.get_all_sessions()
        logger.info(f"{len(sessions)} séance(s) trouvée(s) sur le Google Sheet.")
    except Exception as exc:
        err_msg = f"Impossible de charger les séances depuis Google Sheets : {exc}"
        logger.error(err_msg)
        report["errors"].append(err_msg)
        return report

    for s in sessions:
        try:
            d_str = s.date.isoformat() if isinstance(s.date, date) else str(s.date)
            session_payload = {
                "date": d_str,
                "semaine": s.semaine,
                "statut": s.statut.value if hasattr(s.statut, "value") else str(s.statut),
                "type_seance": s.type_seance.value if hasattr(s.type_seance, "value") else str(s.type_seance),
                "distance_km": s.distance_km,
                "denivele_d_plus": s.denivele_d_plus or 0,
                "duree_secondes": s.duree_secondes,
                "ressenti_rpe": s.ressenti_rpe,
                "fc_moyenne": s.fc_moyenne,
                "fc_max": s.fc_max,
                "meteo_note": s.meteo_note,
                "programme": s.programme or "",
                "remarques": s.remarques or "",
                "notes": s.notes or "",
                "allure_cible": s.allure_cible,
                "vitesse_cible": s.vitesse_cible,
                "strava_id": s.strava_id,
            }

            if not dry_run:
                # Vérifier si une séance existe déjà à cette date pour garantir l'idempotence
                existing_sessions = db_manager.get_sport_sessions(start_date=d_str, end_date=d_str)
                matching = None
                type_val = session_payload["type_seance"]
                for ex in existing_sessions:
                    if ex.get("type_seance") == type_val:
                        matching = ex
                        break

                if matching:
                    db_manager.update_sport_session(matching["id"], session_payload)
                elif existing_sessions and len(existing_sessions) == 1 and not s.strava_id:
                    # Une seule séance à cette date, on met à jour
                    db_manager.update_sport_session(existing_sessions[0]["id"], session_payload)
                else:
                    db_manager.add_sport_session(session_payload)

            report["sessions_migrated"] += 1
        except Exception as exc:
            err = f"Erreur lors de la migration de la séance du {s.date} : {exc}"
            logger.warning(err)
            report["errors"].append(err)

    # 2. Migration des synthèses hebdomadaires
    try:
        summaries: List[SportWeeklySummary] = sport_connector.get_all_summaries()
        logger.info(f"{len(summaries)} synthèse(s) hebdomadaire(s) trouvée(s) sur le Google Sheet.")
    except Exception as exc:
        err_msg = f"Impossible de charger les synthèses depuis Google Sheets : {exc}"
        logger.warning(err_msg)
        summaries = []

    for summ in summaries:
        try:
            summary_payload = {
                "semaine": summ.semaine,
                "annee": summ.annee,
                "nb_seances": summ.nb_seances,
                "km_total": summ.km_total,
                "d_plus_total": summ.d_plus_total,
                "km_effort_total": summ.km_effort_total,
                "duree_secondes": summ.duree_secondes,
                "charge_rpe_totale": summ.charge_rpe_totale,
                "nb_renfo": summ.nb_renfo,
                "previous_week_km_effort": summ.previous_week_km_effort,
                "vitesse_moyenne_kmh": summ.vitesse_moyenne_kmh,
                "previous_week_vitesse_kmh": summ.previous_week_vitesse_kmh,
                "previous_week_charge_rpe": summ.previous_week_charge_rpe,
                "duree_course_secondes": summ.duree_course_secondes,
            }

            if not dry_run:
                db_manager.upsert_sport_weekly_summary(summary_payload)

            report["summaries_migrated"] += 1
        except Exception as exc:
            err = f"Erreur lors de la migration de la synthèse S{summ.semaine}-{summ.annee} : {exc}"
            logger.warning(err)
            report["errors"].append(err)

    return report


def main() -> None:
    """Point d'entrée CLI pour exécuter la migration."""
    parser = argparse.ArgumentParser(description="Migration des données sportives Google Sheets vers SQLite.")
    parser.add_argument("--db-path", default=None, help="Chemin du fichier SQLite (défaut: hub_data.db)")
    parser.add_argument("--dry-run", action="store_true", help="Simule l'aspiration sans insérer en base")
    args = parser.parse_args()

    db = DatabaseManager(db_path=args.db_path) if args.db_path else get_database_manager()
    db.init_db()

    try:
        connector = SportConnector()
    except Exception as exc:
        logger.error(f"Impossible d'initialiser SportConnector (Google Sheets) : {exc}")
        sys.exit(1)

    logger.info(f"Démarrage de la migration vers {db.db_path} (dry_run={args.dry_run})...")
    res = migrate_sheets_to_sqlite(connector, db, dry_run=args.dry_run)

    logger.info("=== Bilan de migration ===")
    logger.info(f"Séances migrées : {res['sessions_migrated']}")
    logger.info(f"Synthèses migrées : {res['summaries_migrated']}")
    if res["errors"]:
        logger.warning(f"Erreurs rencontrées ({len(res['errors'])}) : {res['errors']}")
    else:
        logger.info("Migration réussie avec succès (0 erreur) !")


if __name__ == "__main__":
    main()
