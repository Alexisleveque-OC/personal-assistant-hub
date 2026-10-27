"""Doublure en mémoire du classeur Google Sheets « Repas & Courses » (lectures/écritures cohérentes, hors-ligne).

Reproduit le sous-ensemble de l'API gspread utilisé par `MealsShoppingConnector` et les conventions du vrai
classeur : cases à cocher relues en « TRUE »/« FALSE », onglet annuel « repas AAAA », blocs rayon/article
dans « Cette semaine » à partir de la ligne 10. Données fictives uniquement (dépôt public).
"""
from dataclasses import dataclass, field
from datetime import date, timedelta
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

WEEKDAYS = ("Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche")
WEEK_ITEMS_FIRST_ROW = 10  # 1-indexé, comme dans le vrai onglet « Cette semaine »

DEFAULT_RAYONS = ("Fruits & Légumes", "Frais", "Épicerie", "Boucherie", "Surgelés", "Hygiène", "Entretien", "Divers")
DEFAULT_RECIPES: Tuple[Tuple[str, Sequence[str]], ...] = (
    ("Risotto de quinoa", ("Quinoa", "Courgette", "Bouillon", "Parmesan")),
    ("Gratin de courgettes", ("Courgette", "Crème fraîche", "Gruyère")),
    ("Chili sin carne", ("Haricots rouges", "Maïs", "Tomates concassées", "Oignon")),
    ("Lasagnes", ("Pâtes à lasagnes", "Sauce tomate", "Mozzarella")),
)
DEFAULT_INGREDIENT_RAYONS: Tuple[Tuple[str, str], ...] = (
    ("Lait", "Frais"), ("Beurre", "Frais"), ("Œufs", "Frais"), ("Pain", "Épicerie"), ("Café", "Épicerie"),
    ("Quinoa", "Épicerie"), ("Courgette", "Fruits & Légumes"), ("Bouillon", "Épicerie"), ("Parmesan", "Frais"),
    ("Crème fraîche", "Frais"), ("Gruyère", "Frais"), ("Haricots rouges", "Épicerie"), ("Maïs", "Épicerie"),
    ("Tomates concassées", "Épicerie"), ("Oignon", "Fruits & Légumes"), ("Pâtes à lasagnes", "Épicerie"),
    ("Sauce tomate", "Épicerie"), ("Mozzarella", "Frais"), ("Lessive", "Entretien"),
)


def _cell_text(value: Any) -> str:
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    return "" if value is None else str(value)


class FakeWorksheet:
    def __init__(self, title: str, rows: Iterable[Sequence[Any]], sheet_id: int = 0) -> None:
        self.title = title
        self.id = sheet_id
        self.rows: List[List[str]] = [[_cell_text(v) for v in row] for row in rows]

    def get_all_values(self) -> List[List[str]]:
        return [list(row) for row in self.rows]

    def append_row(self, row: Sequence[Any], value_input_option: Optional[str] = None) -> None:
        self.rows.append([_cell_text(v) for v in row])

    def append_rows(self, rows: Sequence[Sequence[Any]], value_input_option: Optional[str] = None) -> None:
        for row in rows:
            self.append_row(row)

    def update_cell(self, row: int, col: int, value: Any) -> None:
        while len(self.rows) < row:
            self.rows.append([])
        target = self.rows[row - 1]
        while len(target) < col:
            target.append("")
        target[col - 1] = _cell_text(value)

    def batch_update(self, updates: Sequence[Dict[str, Any]], value_input_option: Optional[str] = None) -> None:
        for update in updates:
            match = re.fullmatch(r"([A-Z])(\d+)", update["range"])
            if match is None:
                raise ValueError(f"Plage non supportée par la doublure : {update['range']!r}")
            self.update_cell(int(match.group(2)), ord(match.group(1)) - ord("A") + 1, update["values"][0][0])

    def delete_rows(self, index: int) -> None:
        del self.rows[index - 1]


class FakeSpreadsheet:
    def __init__(self, worksheets: Iterable[FakeWorksheet]) -> None:
        self._worksheets = {ws.title: ws for ws in worksheets}

    def worksheets(self) -> List[FakeWorksheet]:
        return list(self._worksheets.values())

    def worksheet(self, title: str) -> FakeWorksheet:
        if title not in self._worksheets:
            raise LookupError(f"Onglet « {title} » absent de la doublure : {sorted(self._worksheets)}")
        return self._worksheets[title]

    def batch_update(self, body: Dict[str, Any]) -> None:
        """Validation de données (cases à cocher) : sans effet sur le contenu."""


@dataclass
class WeekItem:
    name: str
    rayon: str
    checked: bool = False


@dataclass
class MealsSheetState:
    """État initial du classeur. `meals` : date → (midi, soir)."""
    today: date
    waiting: List[Tuple[str, bool]] = field(default_factory=list)
    week: List[WeekItem] = field(default_factory=list)
    meals: Dict[date, Tuple[str, str]] = field(default_factory=dict)
    recipes: Sequence[Tuple[str, Sequence[str]]] = DEFAULT_RECIPES
    planning_days_before: int = 14
    planning_days_after: int = 28


def build_meals_spreadsheet(state: MealsSheetState) -> FakeSpreadsheet:
    added_at = state.today.strftime("%d/%m/%Y")
    sheets = [
        FakeWorksheet("Liste_Attente", [["Acheté", "Article", "Date d'ajout"]]
                      + [[bought, name, added_at] for name, bought in state.waiting], sheet_id=1),
        FakeWorksheet("Cette semaine", _week_rows(state.week)),
        FakeWorksheet("Recettes", [["Plat", "Catégorie", "Catégorie 2", "Complet", "Ingrédient"]]
                      + [[name, "Plat", "", "TRUE", *ingredients] for name, ingredients in state.recipes]),
        FakeWorksheet("Recette festive", [["Plat", "Catégorie", "Catégorie 2", "Complet", "Ingrédient"]]),
        FakeWorksheet("Rayons", [["Rayons", "Ordre"]] + [[r, i + 1] for i, r in enumerate(DEFAULT_RAYONS)]),
        FakeWorksheet("Ingredients_Rayons", [["Ingrédient", "Rayon"]] + [list(p) for p in DEFAULT_INGREDIENT_RAYONS]),
        FakeWorksheet("Hors_Repas", [["Nom", "pré-cocher?", "rayon"]]),
    ]
    sheets += _planning_sheets(state)
    return FakeSpreadsheet(sheets)


def _week_rows(items: List[WeekItem]) -> List[List[Any]]:
    rows: List[List[Any]] = [["Planning de la semaine"]] + [[] for _ in range(WEEK_ITEMS_FIRST_ROW - 2)]
    by_rayon: Dict[str, List[WeekItem]] = {}
    for item in items:
        by_rayon.setdefault(item.rayon, []).append(item)
    for rayon, rayon_items in by_rayon.items():
        rows.append([rayon, ""])
        rows += [[item.checked, item.name] for item in rayon_items]
    return rows


def _planning_sheets(state: MealsSheetState) -> List[FakeWorksheet]:
    by_year: Dict[int, List[List[Any]]] = {}
    first = state.today - timedelta(days=state.planning_days_before)
    for offset in range(state.planning_days_before + state.planning_days_after + 1):
        day = first + timedelta(days=offset)
        lunch, dinner = state.meals.get(day, ("", ""))
        by_year.setdefault(day.year, []).append(
            [day.strftime("%d/%m/%Y"), WEEKDAYS[day.weekday()], lunch, dinner, ""]
        )
    return [
        FakeWorksheet(f"repas {year}", [["Date", "Jour", "Midi", "Soir", "Notes / Magasin"]] + rows)
        for year, rows in sorted(by_year.items())
    ]


def waiting_rows(sheet: FakeSpreadsheet) -> List[Tuple[str, bool]]:
    """Articles de « Liste_Attente » : (nom, coché)."""
    return [(row[1], row[0] == "TRUE") for row in sheet.worksheet("Liste_Attente").rows[1:] if len(row) > 1 and row[1]]


def week_rows(sheet: FakeSpreadsheet) -> List[Tuple[str, bool]]:
    """Articles de « Cette semaine » (colonne A/B) : (nom, coché)."""
    rows = sheet.worksheet("Cette semaine").rows[WEEK_ITEMS_FIRST_ROW - 1:]
    return [(row[1], row[0] == "TRUE") for row in rows if len(row) > 1 and row[1] and row[0] in ("TRUE", "FALSE")]


def planned_meals(sheet: FakeSpreadsheet) -> Dict[str, Tuple[str, str]]:
    """Planning complet : « JJ/MM/AAAA » → (midi, soir)."""
    meals: Dict[str, Tuple[str, str]] = {}
    for ws in sheet.worksheets():
        if ws.title.startswith("repas "):
            for row in ws.rows[1:]:
                meals[row[0]] = (row[2], row[3])
    return meals
