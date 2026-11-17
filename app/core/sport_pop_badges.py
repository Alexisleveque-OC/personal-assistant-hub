"""Badges pop-culture du catalogue d'origine : Astérix (Otis), Seigneur des Anneaux, Archives de Roshar.
Fonction pure, sans état. Les trophées pop-culture du 16/11 sont dans sport_fun_badges.py.
"""
import re
from typing import List

from app.connectors.sheets.sport_models import BadgeCategory, SportBadge, SportSession


def evaluate_pop_badges(realised: List[SportSession], total_dist: float, total_seances: int) -> List[SportBadge]:
    badges: List[SportBadge] = []

    # --- BADGES POP-CULTURE (Astérix Otis, Seigneur des Anneaux, Roshar) ---
    # 1. Astérix & Obélix : Mission Cléopâtre (Otis)
    # Situation
    otis_sit_unlocked = any("situation" in (s.remarques or "").lower() or "rencontre" in (s.remarques or "").lower() for s in realised)
    badges.append(
        SportBadge(
            id="pop_otis_situation",
            title="Pas de Bonne ou Mauvaise Situation 📜",
            description="Vous savez, moi je ne crois pas qu'il y ait de bonne ou de mauvaise situation...",
            icon="📜",
            category=BadgeCategory.POP_CULTURE,
            is_unlocked=otis_sit_unlocked,
            rarity="or",
        )
    )

    # Pierres & Construction
    otis_pierres_unlocked = any(
        any(w in (s.remarques or "").lower() for w in ["pierre", "construction", "dalle", "chantier"])
        for s in realised
    )
    badges.append(
        SportBadge(
            id="pop_otis_pierres",
            title="Pas de Pierres, Pas de Construction ! 🏛️",
            description="Quand on n'a pas de pierres, on ne peut pas construire... mais on peut faire du renfo !",
            icon="🏛️",
            category=BadgeCategory.POP_CULTURE,
            is_unlocked=otis_pierres_unlocked,
            rarity="bronze",
        )
    )

    # Lion mort
    otis_lion_unlocked = any(
        any(w in (s.remarques or "").lower() for w in ["lion", "désert", "desert", "chaleur écrasante"])
        for s in realised
    )
    badges.append(
        SportBadge(
            id="pop_otis_lion",
            title="Un Lion Mort dans le Désert 🦁",
            description="Courir sous un soleil de plomb digne d'Alexandrie !",
            icon="🦁",
            category=BadgeCategory.POP_CULTURE,
            is_unlocked=otis_lion_unlocked,
            rarity="argent",
        )
    )

    # Scribe d'Alexandrie (notes longues > 25 mots)
    otis_scribe_unlocked = any(len((s.remarques or "").split()) >= 25 for s in realised)
    badges.append(
        SportBadge(
            id="pop_otis_scribe",
            title="Le Scribe d'Alexandrie ✍️",
            description="Rédiger un véritable monologue inspiré dans les remarques de séance !",
            icon="✍️",
            category=BadgeCategory.POP_CULTURE,
            is_unlocked=otis_scribe_unlocked,
            rarity="argent",
        )
    )

    # Deuxième porte à gauche
    otis_porte_unlocked = any(
        (s.allure_secondes and s.allure_secondes < 300) or ("porte" in (s.remarques or "").lower())
        for s in realised
    )
    badges.append(
        SportBadge(
            id="pop_otis_porte_gauche",
            title="Deuxième Porte à Gauche 🚪",
            description="Filez vite ! Séance avec grosse pointe de vitesse ou passage de porte.",
            icon="🚪",
            category=BadgeCategory.POP_CULTURE,
            is_unlocked=otis_porte_unlocked,
            rarity="bronze",
        )
    )

    # Itinéris ne capte plus
    otis_itineris_unlocked = any(
        any(w in (s.remarques or "").lower() for w in ["calme", "déconnexion", "sans musique", "nature", "forêt"])
        for s in realised
    )
    badges.append(
        SportBadge(
            id="pop_otis_itineris",
            title="Itinéris ne Capte Plus 📵",
            description="Courir déconnecté du réseau en pleine nature !",
            icon="📵",
            category=BadgeCategory.POP_CULTURE,
            is_unlocked=otis_itineris_unlocked,
            rarity="bronze",
        )
    )

    # 2. Le Seigneur des Anneaux (LOTR)
    # Road to Mordor (trajet de Frodon : 2 850 km cumulés)
    mordor_target = 2850.0
    mordor_unlocked = total_dist >= mordor_target
    badges.append(
        SportBadge(
            id="pop_lotr_mordor",
            title="Road to Mordor 🌋 (2 850 km)",
            description="Parcourir à pied la distance exacte reliant Cul-de-Sac à la Montagne du Destin !",
            icon="🌋",
            category=BadgeCategory.POP_CULTURE,
            is_unlocked=mordor_unlocked,
            current_value=total_dist,
            target_value=mordor_target,
            unit="km",
            progress_pct=min(100, int((total_dist / mordor_target) * 100)),
            rarity="mythique",
        )
    )

    # Deuxième petit-déjeuner
    lotr_dej_unlocked = any(
        any(w in (s.remarques or "").lower() for w in ["petit-déjeuner", "petit dejeuner", "faim", "croissant"])
        for s in realised
    )
    badges.append(
        SportBadge(
            id="pop_lotr_second_dejeuner",
            title="Le Deuxième Petit-Déjeuner 🥐",
            description="Rentrer de sortie le ventre affamé comme un Hobbit affamé !",
            icon="🥐",
            category=BadgeCategory.POP_CULTURE,
            is_unlocked=lotr_dej_unlocked,
            rarity="bronze",
        )
    )

    # En route pour Fondcombe (135 km)
    fondcombe_target = 135.0
    fondcombe_unlocked = total_dist >= fondcombe_target
    badges.append(
        SportBadge(
            id="pop_lotr_fondcombe",
            title="En Route pour Fondcombe 🧝 (135 km)",
            description="La distance de Hobbitebourg au refuge d'Elrond franchie en baskets !",
            icon="🧝",
            category=BadgeCategory.POP_CULTURE,
            is_unlocked=fondcombe_unlocked,
            current_value=total_dist,
            target_value=fondcombe_target,
            unit="km",
            progress_pct=min(100, int((total_dist / fondcombe_target) * 100)),
            rarity="argent",
        )
    )

    # Vous ne passerez pas ! (D+ > 200m d'un coup ou remarque)
    passerez_unlocked = any(
        (s.denivele_d_plus and s.denivele_d_plus >= 200) or ("passerez pas" in (s.remarques or "").lower())
        for s in realised
    )
    badges.append(
        SportBadge(
            id="pop_lotr_vous_ne_passerez_pas",
            title="Vous Ne Passerez Pas ! 🧙",
            description="Barrer la route au dénivelé sur une ascension redoutable !",
            icon="🧙",
            category=BadgeCategory.POP_CULTURE,
            is_unlocked=passerez_unlocked,
            rarity="argent",
        )
    )

    # L'Anneau Unique (boucle parfaite)
    anneau_unlocked = any(
        any(w in (s.remarques or "").lower() for w in ["boucle", "anneau", "tour du lac", "circuit"])
        for s in realised
    )
    badges.append(
        SportBadge(
            id="pop_lotr_anneau_unique",
            title="L'Anneau Unique 💍",
            description="Boucler un parcours en boucle parfaite sans faire demi-tour !",
            icon="💍",
            category=BadgeCategory.POP_CULTURE,
            is_unlocked=anneau_unlocked,
            rarity="argent",
        )
    )

    # Pas un orque en vue
    orque_unlocked = any(
        any(w in (s.remarques or "").lower() for w in ["brouillard", "brume", "seul", "nappe"])
        for s in realised
    )
    badges.append(
        SportBadge(
            id="pop_lotr_pas_un_orque",
            title="Pas un Orque en Vue 🌫️",
            description="Courir dans la brume matinale enveloppé dans le silence.",
            icon="🌫️",
            category=BadgeCategory.POP_CULTURE,
            is_unlocked=orque_unlocked,
            rarity="bronze",
        )
    )

    # 3. Brandon Sanderson - Les Archives de Roshar
    # Pont Quatre (Bridge Four - RPE 9 ou 10)
    pont4_unlocked = any(
        (s.ressenti_rpe and s.ressenti_rpe >= 9) or ("pont quatre" in (s.remarques or "").lower() or "bridge four" in (s.remarques or "").lower())
        for s in realised
    )
    badges.append(
        SportBadge(
            id="pop_roshar_pont_quatre",
            title="Pont Quatre (Bridge Four) 🪵",
            description="La vie avant la mort, la force avant la faiblesse : surmonter une séance extrême à RPE 9 ou 10 !",
            icon="🪵",
            category=BadgeCategory.POP_CULTURE,
            is_unlocked=pont4_unlocked,
            rarity="or",
        )
    )

    # Haute-Tempête (courir sous la pluie / tempête / déluge)
    tempete_unlocked = any(
        any(w in (s.remarques or "").lower() for w in ["haute-tempête", "haute-tempete", "déluge", "deluge", "tempête", "orage"])
        for s in realised
    )
    badges.append(
        SportBadge(
            id="pop_roshar_haute_tempete",
            title="Au Cœur de la Haute-Tempête ⚡",
            description="Affronter le cataclysme en baskets et en sortir victorieux !",
            icon="⚡",
            category=BadgeCategory.POP_CULTURE,
            is_unlocked=tempete_unlocked,
            rarity="or",
        )
    )

    # Marcheur du Vent (Windrunner - vitesse ou rafales)
    wind_unlocked = any(
        (s.vitesse_kmh and s.vitesse_kmh >= 12.0) or any(w in (s.remarques or "").lower() for w in ["marcheur du vent", "rafales", "voler", "vent de dos"])
        for s in realised
    )
    badges.append(
        SportBadge(
            id="pop_roshar_marcheur_du_vent",
            title="Marcheur du Vent (Windrunner) 💨",
            description="Fendre l'air avec fluidité et vitesse sur le bitume !",
            icon="💨",
            category=BadgeCategory.POP_CULTURE,
            is_unlocked=wind_unlocked,
            rarity="argent",
        )
    )

    # Danseur de Pierre (Stoneward - sentier / cailloux / D+)
    stone_unlocked = any(
        any(w in (s.remarques or "").lower() for w in ["danseur de pierre", "cailloux", "rocher", "roc", "sentier"])
        for s in realised
    )
    badges.append(
        SportBadge(
            id="pop_roshar_danseur_de_pierre",
            title="Danseur de Pierre (Stoneward) 🪨",
            description="Fouler le roc avec la solidité inébranlable d'un radiant !",
            icon="🪨",
            category=BadgeCategory.POP_CULTURE,
            is_unlocked=stone_unlocked,
            rarity="argent",
        )
    )

    # Les Idéaux des Radiants (séances consécutives ou persévérance)
    ideaux_unlocked = total_seances >= 15 or any("idéaux" in (s.remarques or "").lower() or "serment" in (s.remarques or "").lower() for s in realised)
    badges.append(
        SportBadge(
            id="pop_roshar_ideaux_radieux",
            title="Les Idéaux des Radiants 🛡️",
            description="Le voyage avant la destination : 15 séances d'engagement loyal !",
            icon="🛡️",
            category=BadgeCategory.POP_CULTURE,
            is_unlocked=ideaux_unlocked,
            rarity="or",
        )
    )

    # Infusion de Fulgurance (allure record ou énergie)
    fulgurance_unlocked = any(
        (s.allure_secondes and s.allure_secondes <= 315) or ("fulgurance" in (s.remarques or "").lower())
        for s in realised
    )
    badges.append(
        SportBadge(
            id="pop_roshar_fulgurance",
            title="Infusion de Fulgurance 💎",
            description="Briller d'une énergie éclatante sur une séance rapide !",
            icon="💎",
            category=BadgeCategory.POP_CULTURE,
            is_unlocked=fulgurance_unlocked,
            rarity="argent",
        )
    )

    # Le Spren de la Douleur
    spren_unlocked = any(
        any(w in (s.remarques or "").lower() for w in ["spren", "mental", "tenu bon"])
        or re.search(r"\bdur\b", (s.remarques or "").lower())  # mot entier : « durée », « durant » ne comptent pas
        for s in realised
    )
    badges.append(
        SportBadge(
            id="pop_roshar_spren_douleur",
            title="Le Spren de la Douleur 👹",
            description="Triompher de l'inconfort et transformer l'effort en victoire pure !",
            icon="👹",
            category=BadgeCategory.POP_CULTURE,
            is_unlocked=spren_unlocked,
            rarity="bronze",
        )
    )
    return badges
