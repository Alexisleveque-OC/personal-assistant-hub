"""Import d'une séance depuis une capture d'écran déjà analysée par Gemini Vision (logique métier, sans HTTP).

Montre CW500 M : seule la fréquence cardiaque est fiable (fusion sur la séance réalisée, ou séance prévue passée en
réalisée). Sinon : adaptation d'une séance prévue ou ré-import de la même séance, nouvelle séance pour une 2e sortie.
"""
from datetime import date
from typing import Any, Dict

from app.connectors.sheets.sport_models import SportSessionCreate, SportSessionStatus, SportSessionType


class ScreenshotImportError(Exception):
    """Import refusé pour une raison métier ; le message est destiné à l'utilisateur (400 côté routeur)."""


def normalize_session_type(type_str: str) -> SportSessionType:
    """Type de séance lu sur la capture (« Fractionné », « VMA », « Course à pied »…) ; EF par défaut."""
    clean_tp = type_str.strip().lower()
    if "fractionn" in clean_tp or "vma" in clean_tp or "intervalles" in clean_tp:
        return SportSessionType.FRACTIONNE
    elif "longue" in clean_tp:
        return SportSessionType.SORTIE_LONGUE
    elif "renfo" in clean_tp:
        return SportSessionType.RENFORCEMENT
    elif "vitesse" in clean_tp:
        return SportSessionType.VITESSE
    elif "course" in clean_tp:
        return SportSessionType.COURSE
    else:
        try:
            return SportSessionType(type_str)
        except ValueError:
            return SportSessionType.EF


def import_screenshot_session(connector, vision_data: Dict[str, Any], target_date: date, spoken_date: str) -> Dict[str, Any]:
    """Enregistre la séance extraite à `target_date` et renvoie la réponse de l'API (séance, extraction, phrase d'Otis)."""
    app_src = vision_data.get("app_source", "Capture")
    dist = vision_data.get("distance_km")
    duree = vision_data.get("duree_secondes")
    dplus = vision_data.get("denivele_d_plus", 0) or 0
    # Gemini renvoie parfois 0 pour une FC absente de la capture : 0 signifie « non mesurée »
    fc_moy = vision_data.get("fc_moyenne") or None
    fc_max = vision_data.get("fc_max") or None
    titre = vision_data.get("titre") or "Course à pied"
    matched_type = normalize_session_type(vision_data.get("type_seance") or "EF")


    # Decathlon Connect (montre CW500 M) : seule la fréquence cardiaque est fiable.
    # Si une séance réalisée existe déjà à cette date, on ne fusionne que la FC (jamais de doublon).
    app_src_lower = str(app_src).lower()
    is_heart_rate_only_source = "cw500" in app_src_lower or "decathlon connect" in app_src_lower
    if is_heart_rate_only_source:
        realised_same_day = [
            s for s in connector.get_all_sessions()
            if s.date == target_date and s.statut == SportSessionStatus.REALISE
        ]
        if realised_same_day:
            target_session = max(realised_same_day, key=lambda s: s.id or 0)
            if fc_moy is None and fc_max is None:
                raise ScreenshotImportError(
                    f"Aucune fréquence cardiaque lisible sur la capture {app_src} du {target_date.strftime('%d/%m/%Y')}. "
                    f"La séance existante n'a pas été modifiée."
                )
            hr_updates: Dict[str, Any] = {}
            if fc_moy is not None:
                hr_updates["fc_moyenne"] = fc_moy
            if fc_max is not None:
                hr_updates["fc_max"] = fc_max
            note_tag = f"FC importée depuis {app_src}"
            hr_updates["notes"] = f"{target_session.notes} | {note_tag}" if target_session.notes else note_tag
            saved_session = connector.update_session_by_id(target_session.id, hr_updates)

            fc_parts = []
            if fc_moy is not None:
                fc_parts.append(f"moyenne {fc_moy} bpm")
            if fc_max is not None:
                fc_parts.append(f"max {fc_max} bpm")
            spoken = (
                f"Fréquence cardiaque ({', '.join(fc_parts)}) ajoutée à ta séance {spoken_date}. "
                f"Distance et durée existantes conservées."
            )
            return {
                "success": True,
                "app_source": app_src,
                "session": saved_session.model_dump(mode="json"),
                "extracted": vision_data,
                "spoken_response": spoken,
            }

        # Séance seulement prévue : on la passe en Réalisé avec durée + FC, sans la distance de la montre
        planned = connector.get_session(target_date)
        if planned and planned.statut in (SportSessionStatus.PLANIFIE, "Prévu"):
            planned_updates: Dict[str, Any] = {"statut": "Réalisé"}
            if duree is not None:
                planned_updates["duree_secondes"] = duree
            if fc_moy is not None:
                planned_updates["fc_moyenne"] = fc_moy
            if fc_max is not None:
                planned_updates["fc_max"] = fc_max
            note_tag = f"Durée et FC importées depuis {app_src} (distance montre ignorée)"
            planned_updates["notes"] = f"{planned.notes} | {note_tag}" if planned.notes else note_tag
            saved_session = connector.update_session_by_id(planned.id, planned_updates)

            duree_txt = f"{duree // 60} min {duree % 60} s" if duree else "durée non lisible"
            fc_txt = f", FC moyenne {fc_moy} bpm" if fc_moy is not None else ""
            spoken = (
                f"Séance {spoken_date} passée en réalisée : {duree_txt}{fc_txt}. "
                f"La distance de la montre est ignorée, pense à la corriger si besoin."
            )
            return {
                "success": True,
                "app_source": app_src,
                "session": saved_session.model_dump(mode="json"),
                "extracted": vision_data,
                "spoken_response": spoken,
            }

    # Déduplication intelligente : adapter une séance planifiée existante ou insérer une nouvelle
    existing = connector.get_session(target_date)
    should_update_existing = False

    if existing:
        if existing.statut in (SportSessionStatus.PLANIFIE, "Prévu"):
            # Séance planifiée : on l'adapte normalement en séance réalisée
            should_update_existing = True
        elif existing.statut == SportSessionStatus.REALISE:
            # Séance déjà réalisée : vérifier si c'est un ré-import de la même séance (distance très similaire)
            existing_dist = existing.distance_km or 0.0
            new_dist = dist or 0.0
            if abs(existing_dist - new_dist) < 0.2:
                should_update_existing = True
            else:
                # Deuxième séance distincte à la même date : créer une nouvelle entrée pour préserver les deux
                should_update_existing = False

    if existing and should_update_existing:
        updates: Dict[str, Any] = {
            "statut": "Réalisé",
            "distance_km": dist,
            "duree_secondes": duree,
            "denivele_d_plus": dplus,
        }
        if fc_moy is not None:
            updates["fc_moyenne"] = fc_moy
        if fc_max is not None:
            updates["fc_max"] = fc_max
        if existing.programme:
            updates["programme"] = existing.programme
        else:
            updates["programme"] = titre
        if existing.type_seance and existing.type_seance != SportSessionType.EF:
            updates["type_seance"] = existing.type_seance
        else:
            updates["type_seance"] = matched_type

        # Conserver impérativement les remarques existantes de l'utilisateur
        if existing.remarques:
            updates["remarques"] = existing.remarques

        note_tag = f"Import {app_src} : {titre}" if titre else f"Import {app_src}"
        updates["notes"] = f"{existing.notes} | {note_tag}" if existing.notes else note_tag
        saved_session = connector.update_session_by_id(existing.id, updates)
    else:
        new_payload = SportSessionCreate(
            date=target_date,
            statut=SportSessionStatus.REALISE,
            type_seance=matched_type,
            distance_km=dist,
            duree_secondes=duree,
            denivele_d_plus=dplus,
            fc_moyenne=fc_moy,
            fc_max=fc_max,
            programme=titre,
            remarques="",
            notes=f"Import {app_src} : {titre}" if titre else f"Import {app_src}",
        )
        saved_session = connector.log_session(new_payload)

    # Réponse vocale soignée d'Otis
    duree_fmt = ""
    if duree:
        m = duree // 60
        s = duree % 60
        duree_fmt = f"en {m} min {s} s" if s else f"en {m} minutes"
    dist_fmt = f"{dist} km" if dist is not None else ""
    fc_fmt = f" avec une fréquence cardiaque moyenne de {fc_moy} bpm" if fc_moy else ""
    dplus_fmt = f" (D+ {dplus} m)" if dplus else ""

    spoken = (
        f"Séance {app_src} {spoken_date} importée avec succès : {dist_fmt} {duree_fmt}{dplus_fmt}{fc_fmt}. "
        f"La séance est enregistrée dans ton carnet ! Comment étaient tes sensations ou ton ressenti d'effort (RPE de 1 à 10) ?"
    )

    return {
        "success": True,
        "app_source": app_src,
        "session": saved_session.model_dump(mode="json"),
        "extracted": vision_data,
        "spoken_response": spoken,
    }
