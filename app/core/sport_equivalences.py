"""Équivalences insolites du jour (ROADMAP Étape 3, demande du 16/11) : fonctions pures, rien n'est stocké.

4 équivalences par jour, une par famille (D+, distance, énergie, animaux). Chaque famille parcourt sa réserve
dans un ordre mélangé propre à chaque cycle : toutes les références passent une fois avant qu'une revienne,
et jamais deux jours de suite la même. Les chiffres de référence sont des ordres de grandeur courants (« ≈ »).
"""
import random
from dataclasses import dataclass
from datetime import date as dt_date
from typing import Dict, List, Optional, Tuple, Union

from app.connectors.sheets.sport_models import SportFunFact

FAMILIES = ("vertical", "geo", "energy", "animal")
KCAL_PER_KM = 65  # estimation classique déjà utilisée par l'app
CHEETAH_KMH = 100.0
SNAIL_MM_PER_S = 1.0
SECONDS_PER_YEAR = 365 * 24 * 3600


def fr_number(value: float, decimals: int = 1) -> str:
    """Nombre à la française : « 5 940 », « 19,8 », « 5 » (zéros décimaux retirés)."""
    whole, frac = f"{abs(value):,.{decimals}f}".split(".") if decimals else (f"{abs(value):,.0f}", "")
    frac = frac.rstrip("0")
    sign = "-" if value < 0 else ""
    return f"{sign}{whole.replace(',', ' ')}{',' + frac if frac else ''}"


@dataclass(frozen=True)
class Ratio:
    """Comparaison « x fois » / « y % de » une grandeur de référence."""
    id: str
    icon: str
    size: float
    many: str  # gabarit avec {r}, ex. « {r} × la tour Eiffel »
    part: str  # gabarit avec {p}, ex. « {p} % de la tour Eiffel »
    detail: str  # gabarit avec {total} et {size}


@dataclass(frozen=True)
class Food:
    id: str
    icon: str
    kcal: int
    singular: str
    plural: str
    per_unit: str  # « le croissant »


@dataclass(frozen=True)
class Timed:
    """Durée qu'il faudrait à un animal pour couvrir les kilomètres cumulés."""
    id: str
    icon: str
    detail: str


Reference = Union[Ratio, Food, Timed]

_M = "{total} m de D+ cumulés, "
_KM = "{total} km au total, "

REFERENCES: Dict[str, List[Reference]] = {
    "vertical": [
        Ratio("eiffel", "🗼", 300, "{r} × la tour Eiffel", "{p} % de la tour Eiffel", _M + "la tour Eiffel en fait {size}"),
        Ratio("montparnasse", "🏢", 210, "{r} × la tour Montparnasse", "{p} % de la tour Montparnasse",
              _M + "la tour Montparnasse en fait {size}"),
        Ratio("kheops", "🔺", 139, "{r} × la pyramide de Khéops", "{p} % de la pyramide de Khéops",
              _M + "Khéops en fait ≈ {size} aujourd'hui"),
        Ratio("liberte", "🗽", 93, "{r} × la statue de la Liberté", "{p} % de la statue de la Liberté",
              _M + "socle compris, elle en fait {size}"),
        Ratio("burj", "🏙️", 828, "{r} × le Burj Khalifa", "{p} % du Burj Khalifa", _M + "le Burj Khalifa en fait {size}"),
        Ratio("ventoux", "🚴", 1910, "{r} × le mont Ventoux", "{p} % du mont Ventoux", _M + "le Ventoux culmine à ≈ {size}"),
        Ratio("montblanc", "🏔️", 4806, "{r} × le mont Blanc", "{p} % du mont Blanc", _M + "le mont Blanc culmine à ≈ {size}"),
        Ratio("everest", "⛰️", 8849, "{r} × l'Everest", "{p} % de l'Everest", _M + "l'Everest culmine à {size}"),
    ],
    "geo": [
        Ratio("marathon", "🏅", 42.195, "{r} marathons", "{p} % d'un marathon", _KM + "un marathon en fait 42,195"),
        Ratio("gr20", "🏝️", 180, "{r} × le GR20", "{p} % du GR20", _KM + "le GR20 en fait {size}"),
        Ratio("tmb", "🥾", 170, "{r} × le tour du Mont-Blanc", "{p} % du tour du Mont-Blanc",
              _KM + "le tour du Mont-Blanc en fait ≈ {size}"),
        Ratio("compostelle", "🐚", 800, "{r} × le chemin de Compostelle", "{p} % du chemin de Compostelle",
              _KM + "le Camino francés en fait ≈ {size}"),
        Ratio("paris_marseille", "🚄", 660, "{r} × Paris–Marseille", "{p} % de Paris–Marseille",
              _KM + "≈ {size} à vol d'oiseau"),
        Ratio("manche", "🌊", 33, "{r} × la traversée de la Manche", "{p} % de la traversée de la Manche",
              _KM + "Calais–Douvres en fait ≈ {size}"),
        Ratio("loire", "🏞️", 1000, "{r} × la Loire", "{p} % de la Loire", _KM + "la Loire en fait ≈ {size}"),
        Ratio("annecy_geneve", "🏔️", 42, "{r} × Annecy–Genève", "{p} % d'Annecy–Genève", _KM + "Annecy–Genève en fait ≈ {size}"),
        Ratio("lune", "🌕", 384400, "{r} × la distance Terre–Lune", "{p} % de la distance Terre–Lune",
              _KM + "la Lune est à ≈ {size}"),
    ],
    "energy": [
        Food("croissant", "🥐", 250, "croissant", "croissants", "le croissant"),
        Food("pain_chocolat", "🍫", 280, "pain au chocolat", "pains au chocolat", "le pain au chocolat"),
        Food("baguette", "🥖", 700, "baguette", "baguettes", "la baguette"),
        Food("pizza", "🍕", 800, "pizza margherita", "pizzas margherita", "la pizza"),
        Food("tablette", "🍬", 540, "tablette de chocolat", "tablettes de chocolat", "la tablette de 100 g"),
        Food("banane", "🍌", 90, "banane", "bananes", "la banane"),
        Food("crepe", "🥞", 150, "crêpe au sucre", "crêpes au sucre", "la crêpe"),
    ],
    "animal": [
        Ratio("sterne", "🐦", 70000, "{r} × la migration d'une sterne arctique", "{p} % de la migration d'une sterne arctique",
              "elle parcourt ≈ 70 000 km par an, record du règne animal"),
        Ratio("monarque", "🦋", 4000, "{r} × la migration du papillon monarque", "{p} % de la migration du papillon monarque",
              "≈ 4 000 km du Canada au Mexique, avec des ailes de 0,5 g"),
        Ratio("baleine", "🐋", 8000, "{r} × la migration d'une baleine à bosse", "{p} % de la migration d'une baleine à bosse",
              "≈ 8 000 km entre zones de nourrissage et de reproduction"),
        Ratio("manchot", "🐧", 100, "{r} × la marche des manchots empereurs", "{p} % de la marche des manchots empereurs",
              "≈ 100 km sur la banquise jusqu'à leur colonie"),
        Ratio("colibri", "🪶", 800, "{r} × la traversée d'un colibri à gorge rubis",
              "{p} % de la traversée d'un colibri à gorge rubis", "≈ 800 km sans escale au-dessus du golfe du Mexique"),
        Timed("guepard", "🐆", "lancé à ≈ 100 km/h… s'il tenait plus de quelques centaines de mètres"),
        Timed("escargot", "🐌", "à ≈ 1 mm/s, sans pause ni salade"),
    ],
}


# ---------- Tirage du jour ----------

def _cycle_order(family: str, cycle: int, size: int) -> List[int]:
    order = random.Random(f"{family}:{cycle}").sample(range(size), size)
    previous_last = random.Random(f"{family}:{cycle - 1}").sample(range(size), size)[-1]
    if order[0] == previous_last:  # pas deux jours de suite la même (l'échange ne touche pas au dernier)
        order[0], order[1] = order[1], order[0]
    return order


def reference_index(family: str, day: dt_date) -> int:
    """Indice de la référence du jour dans la réserve de la famille."""
    size = len(REFERENCES[family])
    cycle, position = divmod(day.toordinal(), size)
    return _cycle_order(family, cycle, size)[position]


# ---------- Mise en forme ----------

def _ratio_texts(ref: Ratio, total: float, unit_decimals: int) -> Tuple[str, str]:
    ratio = total / ref.size
    if ratio >= 1:
        headline = ref.many.format(r=fr_number(round(ratio, 1)))
    else:
        pct = ratio * 100
        headline = ref.part.format(p=fr_number(pct, 1) if pct < 10 else fr_number(int(pct), 0))
    detail = ref.detail.format(total=fr_number(total, unit_decimals), size=fr_number(ref.size, 3))
    return headline, detail


def _food_texts(ref: Food, total_km: float) -> Tuple[str, str]:
    kcal = int(total_km * KCAL_PER_KM)
    count = kcal / ref.kcal
    shown = fr_number(round(count)) if count >= 10 else fr_number(round(count, 1))
    label = ref.plural if count >= 2 else ref.singular
    return f"{shown} {label}", f"environ {fr_number(kcal)} kcal brûlées, ≈ {ref.kcal} kcal {ref.per_unit}"


def _timed_texts(ref: Timed, total_km: float) -> Tuple[str, str]:
    if ref.id == "guepard":
        minutes = round(total_km / CHEETAH_KMH * 60)
        hours, mins = divmod(minutes, 60)
        duration = f"{hours} h {mins:02d}" if hours else f"{mins} min"
        return f"{duration} pour un guépard", ref.detail
    seconds = total_km * 1_000_000 / SNAIL_MM_PER_S
    years = seconds / SECONDS_PER_YEAR
    duration = f"{fr_number(round(years, 1))} ans" if years >= 1 else f"{round(seconds / 86400)} jours"
    return f"{duration} pour un escargot", ref.detail


def _family_of(ref: Reference) -> str:
    return next(family for family, refs in REFERENCES.items() if ref in refs)


def equivalence_for(ref: Reference, total_km: float, total_dplus: int) -> Optional[SportFunFact]:
    family = _family_of(ref)
    if family == "vertical":
        if total_dplus <= 0:
            return None
        headline, detail = _ratio_texts(ref, float(total_dplus), 0)
    else:
        if total_km <= 0:
            return None
        if isinstance(ref, Food):
            headline, detail = _food_texts(ref, total_km)
        elif isinstance(ref, Timed):
            headline, detail = _timed_texts(ref, total_km)
        else:
            headline, detail = _ratio_texts(ref, total_km, 2)
    return SportFunFact(
        id=f"fact_{family}_{ref.id}", title=headline, text=f"{headline} ({detail}) !", icon=ref.icon,
        category=family, headline=headline, detail=detail,
    )


def daily_equivalences(total_km: float, total_dplus: int, day: dt_date) -> List[SportFunFact]:
    """Les équivalences du jour, une par famille (une famille sans données est omise)."""
    facts = []
    for family in FAMILIES:
        fact = equivalence_for(REFERENCES[family][reference_index(family, day)], total_km, total_dplus)
        if fact:
            facts.append(fact)
    return facts
