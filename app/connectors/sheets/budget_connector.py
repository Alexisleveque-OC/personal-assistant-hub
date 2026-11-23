"""Connecteur Google Sheets du classeur Budget (Phase 10) : lecture des catégories, restes, revenus, échéanciers.

Le classeur est aussi piloté par un Apps Script (menu « Budget ») : ce connecteur en suit les règles
(mois actif = dernière case cochée en ligne 4 de `Total dépenses`, mots-clés de `Tri auto`). Les valeurs
sont lues brutes (`UNFORMATTED_VALUE` : nombres, booléens, dates en numéros de série) et mises en cache
par onglet (règle 8) ; toute anomalie de structure lève une erreur qui cite l'attendu et le disponible.
"""
import base64
import difflib
import json
import time
import unicodedata
from datetime import date, timedelta
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from app.connectors.sheets.budget_models import (
    AutoSortRule,
    BudgetCategory,
    BudgetMonth,
    CategoryRemaining,
    CategoryResolution,
    IncomeSummary,
    Installment,
)
from app.core.clock import paris_today

try:
    import gspread
except ImportError:  # pragma: no cover - dépendance du requirements.txt
    gspread = None

SHEETS_EPOCH = date(1899, 12, 30)
CACHE_TTL_SECONDS = 180
CLOSE_MATCH_CUTOFF = 0.8

TOTAL_SHEET = "Total dépenses"
GESTION_SHEET = "Gestion"
CATEGORIES_SHEET = "Catégories"
AUTO_SORT_SHEET = "Tri auto"
INCOME_SHEET = "Revenus"
INSTALLMENTS_SHEET = "Échéanciers"

EXPECTED_HEADERS: Dict[str, Tuple[str, ...]] = {
    CATEGORIES_SHEET: ("Catégorie", "Date de création", "Date de fin"),
    AUTO_SORT_SHEET: ("Nom", "Catégorie"),
    INCOME_SHEET: ("Date", "Montant", "Type"),
    INSTALLMENTS_SHEET: (
        "Nom du Projet", "Montant Total", "Nb Échéances", "Échéance Actuelle", "Mensualité", "Mois Début",
        "Catégorie", "Commentaires", "Statut",
    ),
}
GESTION_MONTHS_ROW = 1  # index 0 : ligne 2 (mois en numéro de série)
GESTION_FIRST_MONTH_COL = 5  # index 0 : colonne F, puis un bloc Prévu | Equilibrage | Reste fin du mois
GESTION_REMAINING_COL = 1  # colonne B : reste total
TOTAL_MONTHS_ROW, TOTAL_CHECKS_ROW, TOTAL_FIRST_MONTH_COL = 1, 3, 3  # lignes 2 et 4, à partir de D


class BudgetConnectorError(Exception):
    """Erreur de base du connecteur Budget."""


class BudgetWorksheetNotFoundError(BudgetConnectorError):
    """Onglet attendu absent du classeur."""


class BudgetHeaderError(BudgetConnectorError):
    """En-têtes d'un onglet différents de ceux attendus (structure du classeur modifiée)."""


class BudgetCategoryNotFoundError(BudgetConnectorError):
    """Catégorie absente de `Gestion`."""


class BudgetMonthNotFoundError(BudgetConnectorError):
    """Mois absent de la ligne 2 de `Gestion`."""


class ActiveMonthNotFoundError(BudgetConnectorError):
    """Aucune case cochée en ligne 4 de `Total dépenses`."""


class InstallmentNotFoundError(BudgetConnectorError):
    """Aucun échéancier de ce nom."""


def normalize(text: str) -> str:
    """Minuscules, sans accents, espaces fusionnés (comparaisons de noms dictés et du classeur)."""
    decomposed = unicodedata.normalize("NFKD", str(text))
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(stripped.lower().split())


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _cell(row: Sequence[Any], index: int) -> Any:
    return row[index] if index < len(row) else ""


def open_budget_spreadsheet(settings: Any) -> Any:
    """Ouvre le classeur `SPREADSHEET_BUDGET_ID` avec le compte de service (même configuration que Repas)."""
    spreadsheet_id = (settings.spreadsheet_budget_id or "").strip()
    if not spreadsheet_id:
        raise BudgetConnectorError(
            "SPREADSHEET_BUDGET_ID n'est pas renseigné : ajoutez l'identifiant du classeur Budget dans .env "
            "(et dans les secrets de déploiement)."
        )
    if gspread is None:
        raise BudgetConnectorError("Le module gspread n'est pas installé.")
    raw_info = (getattr(settings, "google_service_account_info", "") or "").strip()
    if raw_info:
        decoded = raw_info if raw_info.startswith("{") else base64.b64decode(raw_info).decode("utf-8")
        client = gspread.service_account_from_dict(json.loads(decoded))
    else:
        client = gspread.service_account(filename=settings.google_service_account_file)
    return client.open_by_key(spreadsheet_id)


class BudgetConnector:
    def __init__(
        self,
        spreadsheet: Any,
        ttl_seconds: int = CACHE_TTL_SECONDS,
        monotonic: Callable[[], float] = time.monotonic,
        today: Callable[[], date] = paris_today,
    ) -> None:
        self._spreadsheet = spreadsheet
        self._ttl_seconds = ttl_seconds
        self._monotonic = monotonic
        self._today = today
        self._cache: Dict[str, Tuple[float, List[List[Any]]]] = {}

    @classmethod
    def from_settings(cls, settings: Any) -> "BudgetConnector":
        return cls(open_budget_spreadsheet(settings))

    # --- Lecture brute et cache ------------------------------------------------------------------

    def invalidate_cache(self, title: Optional[str] = None) -> None:
        """Oublie un onglet (après une écriture) ou tout le classeur."""
        if title is None:
            self._cache.clear()
        else:
            self._cache.pop(title, None)

    def _values(self, title: str) -> List[List[Any]]:
        cached = self._cache.get(title)
        if cached and self._monotonic() - cached[0] < self._ttl_seconds:
            return cached[1]
        rows = self._worksheet(title).get_all_values(value_render_option="UNFORMATTED_VALUE")
        self._cache[title] = (self._monotonic(), rows)
        return rows

    def _worksheet(self, title: str) -> Any:
        not_found: Tuple[type, ...] = (LookupError,)
        if gspread is not None:
            not_found += (gspread.WorksheetNotFound,)
        try:
            return self._spreadsheet.worksheet(title)
        except not_found:
            available = [ws.title for ws in self._spreadsheet.worksheets()]
            raise BudgetWorksheetNotFoundError(
                f"Onglet « {title} » introuvable dans le classeur Budget. Onglets disponibles : {available}"
            ) from None

    def _table(self, title: str) -> List[List[Any]]:
        """Lignes de données d'un onglet tabulaire après contrôle de ses en-têtes."""
        rows = self._values(title)
        expected = EXPECTED_HEADERS[title]
        found = tuple(str(_cell(rows[0] if rows else [], i)).strip() for i in range(len(expected)))
        if found != expected:
            raise BudgetHeaderError(
                f"En-têtes inattendus dans « {title} » : attendu {list(expected)}, trouvé {list(found)}."
            )
        return rows[1:]

    # --- Conversions -----------------------------------------------------------------------------

    @staticmethod
    def _date(value: Any, where: str) -> date:
        if not _is_number(value):
            raise BudgetConnectorError(f"Date invalide {value!r} ({where}) : numéro de série de date attendu.")
        return SHEETS_EPOCH + timedelta(days=int(value))

    @staticmethod
    def _amount(value: Any, where: str) -> float:
        if not _is_number(value):
            raise BudgetConnectorError(f"Montant invalide {value!r} ({where}) : nombre attendu.")
        return round(float(value), 2)  # les formules du classeur laissent du bruit flottant (923.1539999…)

    def _month(self, value: Any, where: str) -> BudgetMonth:
        day = self._date(value, where)
        return BudgetMonth(year=day.year, month=day.month)

    # --- Catégories et tri auto ------------------------------------------------------------------

    def get_categories(self, active_only: bool = False) -> List[BudgetCategory]:
        categories = []
        for index, row in enumerate(self._table(CATEGORIES_SHEET), start=2):
            name = _cell(row, 0)
            if _is_blank(name):
                continue
            where = f"« {CATEGORIES_SHEET} » ligne {index}"
            created, ended = _cell(row, 1), _cell(row, 2)
            categories.append(BudgetCategory(
                name=str(name),
                created=None if _is_blank(created) else self._date(created, where),
                ended=None if _is_blank(ended) else self._date(ended, where),
            ))
        if active_only:
            today = self._today()
            categories = [c for c in categories if c.is_active(today)]
        return categories

    def get_auto_sort_rules(self) -> List[AutoSortRule]:
        return [
            AutoSortRule(keyword=str(row[0]).strip(), category=str(row[1]))
            for row in self._table(AUTO_SORT_SHEET)
            if not _is_blank(_cell(row, 0)) and not _is_blank(_cell(row, 1))
        ]

    def resolve_category(self, spoken: str) -> CategoryResolution:
        """Catégorie exacte (sans accents ni casse) → mot-clé de `Tri auto` → nom proche unique → question ou inconnue.

        Un seul nom proche est retenu sans question (décision du 23/11 : l'utilisateur corrige si besoin) ;
        plusieurs choix possibles → question, jamais de choix au hasard.
        """
        wanted = normalize(spoken)
        if not wanted:
            raise ValueError("Catégorie vide : précisez la catégorie de la dépense ou du revenu.")
        categories = {normalize(c.name): c.name for c in self.get_categories(active_only=True)}
        if wanted in categories:
            return CategoryResolution(spoken=spoken, status="resolved", category=categories[wanted], source="category")

        padded = f" {wanted} "
        matches = sorted({
            rule.category for rule in self.get_auto_sort_rules()
            if f" {normalize(rule.keyword)} " in padded or padded in f" {normalize(rule.keyword)} "
        })
        if len(matches) == 1:
            return CategoryResolution(spoken=spoken, status="resolved", category=matches[0], source="auto_sort")
        if matches:
            return CategoryResolution(spoken=spoken, status="ambiguous", candidates=matches)

        close: List[str] = difflib.get_close_matches(wanted, list(categories), n=3, cutoff=CLOSE_MATCH_CUTOFF)
        if not close:  # mot(s) dicté(s) contenu(s) dans le nom (« salaire » → Salaire Alexis, Salaire Amélie)
            words = set(wanted.split())
            close = [name for name in categories if words <= set(name.split())]
        if len(close) == 1:
            return CategoryResolution(spoken=spoken, status="resolved", category=categories[close[0]], source="close_match")
        if close:
            return CategoryResolution(spoken=spoken, status="ambiguous", candidates=[categories[c] for c in close])
        return CategoryResolution(spoken=spoken, status="unknown")

    # --- Mois actif ------------------------------------------------------------------------------

    def get_active_month(self) -> BudgetMonth:
        rows = self._values(TOTAL_SHEET)
        months = _cell(rows, TOTAL_MONTHS_ROW) or []
        checks = _cell(rows, TOTAL_CHECKS_ROW) or []
        for col in range(len(checks) - 1, TOTAL_FIRST_MONTH_COL - 1, -1):
            if checks[col] is True:
                return self._month(_cell(months, col), f"« {TOTAL_SHEET} » ligne 2, colonne {col + 1}")
        raise ActiveMonthNotFoundError(
            f"Aucun mois coché en ligne 4 de « {TOTAL_SHEET} » (à partir de la colonne D) : "
            "cochez la case du mois en cours."
        )

    # --- Gestion : reste par catégorie -----------------------------------------------------------

    def get_remaining(self, category: str, month: Optional[BudgetMonth] = None) -> CategoryRemaining:
        """Reste total (colonne B) et reste fin du mois (`month`, sinon le mois actif) d'une catégorie.

        Un nom de groupe (Loisir, Courants…) donne la somme de ses catégories, comme sa ligne « Total »
        (décision du 23/11) ; une catégorie homonyme de son groupe (« Epargne ») l'emporte.
        """
        rows = self._values(GESTION_SHEET)
        target = month or self.get_active_month()
        name, lines, members = self._gestion_lines(rows, category)
        col = self._gestion_month_col(rows, target) + 2
        total = month_total = 0.0
        for line in lines:
            where = f"« {GESTION_SHEET} », {line[0]}"
            total += self._amount(_cell(line, GESTION_REMAINING_COL), f"{where}, colonne B")
            month_total += self._amount(_cell(line, col), f"{where}, reste de {target.label}")
        return CategoryRemaining(
            category=name,
            total_remaining=round(total, 2),
            month=target,
            month_remaining=round(month_total, 2),
            group_categories=members,
        )

    @staticmethod
    def _gestion_groups(rows: List[List[Any]]) -> Dict[int, List[int]]:
        """Groupes de `Gestion` (index de la ligne d'en-tête → index de ses catégories), après la 1re ligne vide."""
        groups: Dict[int, List[int]] = {}
        current: Optional[int] = None
        seen_blank = False
        for index, row in enumerate(rows):
            label = _cell(row, 0)
            if _is_blank(label):
                seen_blank, current = True, None
            elif not seen_blank:
                continue
            elif current is None:
                current = index
                groups[current] = []
            elif normalize(label).startswith("total"):
                current = None
            else:
                groups[current].append(index)
        return groups

    def _gestion_lines(self, rows: List[List[Any]], category: str) -> Tuple[str, List[List[Any]], List[str]]:
        """(nom, lignes à additionner, catégories du groupe) : une ligne pour une catégorie, toutes pour un groupe."""
        wanted = normalize(category)
        groups = self._gestion_groups(rows)
        category_rows = [i for members in groups.values() for i in members]
        found = [i for i in category_rows if normalize(rows[i][0]) == wanted]
        if len(found) > 1:
            raise BudgetCategoryNotFoundError(
                f"Catégorie « {category} » présente {len(found)} fois dans « {GESTION_SHEET} » "
                f"(lignes {[i + 1 for i in found]}) : impossible de choisir."
            )
        if found:
            return str(rows[found[0]][0]), [rows[found[0]]], []
        for header, members in groups.items():
            if normalize(rows[header][0]) == wanted:
                return str(rows[header][0]), [rows[i] for i in members], [str(rows[i][0]) for i in members]
        raise BudgetCategoryNotFoundError(
            f"Catégorie « {category} » introuvable dans « {GESTION_SHEET} ». "
            f"Catégories disponibles : {[str(rows[i][0]) for i in category_rows]}"
        )

    def _gestion_month_col(self, rows: List[List[Any]], month: BudgetMonth) -> int:
        months_row = _cell(rows, GESTION_MONTHS_ROW) or []
        if str(_cell(months_row, 0)).strip() != "Mois":
            raise BudgetHeaderError(
                f"Ligne 2 de « {GESTION_SHEET} » inattendue : « Mois » attendu en A2, trouvé {_cell(months_row, 0)!r}."
            )
        available: Dict[BudgetMonth, int] = {}
        for col in range(GESTION_FIRST_MONTH_COL, len(months_row), 3):
            value = months_row[col]
            if _is_number(value):
                available[self._month(value, f"« {GESTION_SHEET} » ligne 2")] = col
        if month not in available:
            raise BudgetMonthNotFoundError(
                f"Mois {month.label} absent de la ligne 2 de « {GESTION_SHEET} ». "
                f"Mois disponibles : {[m.label for m in available]}"
            )
        col = available[month]
        header = _cell(_cell(rows, 0) or [], col + 2)
        if normalize(header) != "reste fin du mois":
            raise BudgetHeaderError(
                f"Bloc de {month.label} inattendu dans « {GESTION_SHEET} » : « Reste fin du mois » attendu "
                f"en ligne 1, colonne {col + 3}, trouvé {header!r}."
            )
        return col

    # --- Revenus ---------------------------------------------------------------------------------

    def get_income(self, income_type: Optional[str], month: BudgetMonth) -> IncomeSummary:
        """Somme des revenus d'un type (casse et accents ignorés), ou de tous si `income_type` est None, sur un mois."""
        wanted = None if income_type is None else normalize(income_type)
        total, count = 0.0, 0
        for index, row in enumerate(self._table(INCOME_SHEET), start=2):
            if all(_is_blank(_cell(row, i)) for i in range(3)):
                continue
            where = f"« {INCOME_SHEET} » ligne {index}"
            day = self._date(_cell(row, 0), where)
            amount = self._amount(_cell(row, 1), where)
            if (wanted is None or normalize(_cell(row, 2)) == wanted) and month.contains(day):
                total += amount
                count += 1
        return IncomeSummary(income_type=income_type, month=month, total=round(total, 2), count=count)

    # --- Échéanciers -----------------------------------------------------------------------------

    def get_installments(self, active_only: bool = True) -> List[Installment]:
        installments = []
        for index, row in enumerate(self._table(INSTALLMENTS_SHEET), start=2):
            if _is_blank(_cell(row, 0)):
                continue
            where = f"« {INSTALLMENTS_SHEET} » ligne {index}"
            installments.append(Installment(
                name=str(row[0]),
                total_amount=self._amount(_cell(row, 1), where),
                installments_count=int(self._amount(_cell(row, 2), where)),
                current_installment=int(self._amount(_cell(row, 3), where)),
                monthly_amount=self._amount(_cell(row, 4), where),
                start_month=self._month(_cell(row, 5), where),
                category=str(_cell(row, 6)),
                comment=str(_cell(row, 7)),
                status=str(_cell(row, 8)).strip(),
            ))
        if active_only:
            installments = [i for i in installments if normalize(i.status) == "actif"]
        return installments

    def find_installments(self, name: str) -> List[Installment]:
        """Échéanciers (actifs ou terminés) dont le nom correspond, sans accents ni casse."""
        everything = self.get_installments(active_only=False)
        found = [i for i in everything if normalize(i.name) == normalize(name)]
        if not found:
            raise InstallmentNotFoundError(
                f"Aucun échéancier nommé « {name} ». Échéanciers existants : {sorted({i.name for i in everything})}"
            )
        return found
