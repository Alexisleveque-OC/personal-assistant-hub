"""Connecteur Google Sheets du classeur Budget (Phase 10) : catégories, restes, revenus, échéanciers, saisies.

Le classeur est aussi piloté par un Apps Script (menu « Budget ») : ce connecteur en suit les règles
(mois actif = dernière case cochée en ligne 4 de `Total dépenses`, mots-clés de `Tri auto`). Les valeurs
sont lues brutes (`UNFORMATTED_VALUE` : nombres, booléens, dates en numéros de série) et mises en cache
par onglet (règle 8) ; toute anomalie de structure lève une erreur qui cite l'attendu et le disponible.

Écritures (dépenses, revenus, échéanciers, dépenses multiples) : `USER_ENTERED` à la première ligne vide sous les données, comme `getLastRow()+1`
de l'Apps Script, après relecture fraîche de l'onglet ; une ligne écrite est retrouvée par son contenu (l'import
bancaire ajoute des lignes entre-temps) et n'est modifiée ou supprimée que si elle est restée identique.
"""
import base64
import difflib
import json
import time
import unicodedata
from datetime import date, timedelta
from typing import Any, Callable, Collection, Dict, List, Optional, Sequence, Tuple, Union

from app.connectors.sheets.budget_models import (
    AutoSortRule,
    BudgetCategory,
    BudgetCategoryLine,
    BudgetGroup,
    BudgetMonth,
    BudgetEntry,
    BudgetOverview,
    CategoryRemaining,
    CategoryResolution,
    IncomeSummary,
    Installment,
    MonthlyTotals,
    NewInstallment,
    SplitExpense,
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
DEBIT_SHEET = "Débit"
SWILE_SHEET = "Swile"
SPLITS_SHEET = "Dépenses Multiples"

EXPECTED_HEADERS: Dict[str, Tuple[str, ...]] = {
    CATEGORIES_SHEET: ("Catégorie", "Date de création", "Date de fin"),
    AUTO_SORT_SHEET: ("Nom", "Catégorie"),
    INCOME_SHEET: ("Date", "Montant", "Type"),
    DEBIT_SHEET: ("Date", "Montant", "Type", "Commentaires"),  # colonne E (intitulé) sans en-tête dans le classeur
    SWILE_SHEET: ("Date", "Montant", "Type", "Commentaires"),
    INSTALLMENTS_SHEET: (
        "Nom du Projet", "Montant Total", "Nb Échéances", "Échéance Actuelle", "Mensualité", "Mois Début",
        "Catégorie", "Commentaires", "Statut",
    ),
    SPLITS_SHEET: (
        "Date Approximative", "Mot-clé Banque", "Montant Total", "Statut", "Description du Split", "Splits JSON",
    ),
}
GESTION_MONTHS_ROW = 1  # index 0 : ligne 2 (mois en numéro de série)
GESTION_FIRST_MONTH_COL = 5  # index 0 : colonne F, puis un bloc Prévu | Equilibrage | Reste fin du mois
GESTION_REMAINING_COL = 1  # colonne B : reste total
TOTAL_MONTHS_ROW, TOTAL_CHECKS_ROW, TOTAL_FIRST_MONTH_COL = 1, 3, 3  # lignes 2 et 4, à partir de D
TOTAL_EXPENSES_ROW, TOTAL_INCOME_ROW, TOTAL_SAVED_ROW = 4, 5, 6  # lignes 5 à 7 : totaux du mois
TOTAL_LINE_LABELS = {TOTAL_EXPENSES_ROW: "Total dépense", TOTAL_INCOME_ROW: "Total revenus", TOTAL_SAVED_ROW: "Total épargné"}
TOTAL_FIRST_GROUP_ROW = 7  # ligne 8 : premier groupe, sans ligne vide avant lui
INCOME_GROUP = "Revenus"
ENTRY_CATEGORY_COL = "C"
INSTALLMENT_ACTIVE, SPLIT_TO_PROCESS = "Actif", "A traiter"
# Formats posés par l'Apps Script sur ses lignes (une ligne ajoutée par l'API n'hérite d'aucun format).
CURRENCY_FORMAT = {"numberFormat": {"type": "CURRENCY", "pattern": "#,##0.00 €"}}
MONTH_FORMAT = {"numberFormat": {"type": "DATE", "pattern": "mmmm yyyy"}}
DAY_FORMAT = {"numberFormat": {"type": "DATE", "pattern": "dd/mm/yyyy"}}

WrittenRow = Union[BudgetEntry, NewInstallment, SplitExpense]


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


class BudgetEntryChangedError(BudgetConnectorError):
    """Ligne écrite par Otis introuvable telle quelle : supprimée ou modifiée depuis."""


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
        # Les formules du classeur laissent du bruit flottant (923.1539999…, -1e-12) ; « + 0.0 » efface le zéro négatif.
        return round(float(value), 2) + 0.0

    def _optional_amount(self, value: Any, where: str) -> float:
        """Montant d'une cellule laissée vide quand il n'y a rien (Prévu, Equilibrage, dépensé du mois) : vide = 0."""
        return 0.0 if _is_blank(value) else self._amount(value, where)

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

    def resolve_category(self, spoken: str, among: Optional[Collection[str]] = None) -> CategoryResolution:
        """Catégorie exacte (sans accents ni casse) → mot-clé de `Tri auto` → nom proche unique → question ou inconnue.

        Un seul nom proche est retenu sans question (décision du 23/11 : l'utilisateur corrige si besoin) ;
        plusieurs choix possibles → question, jamais de choix au hasard. `among` : seules ces catégories sont
        candidates (ex. celles du groupe Revenus pour un revenu).
        """
        wanted = normalize(spoken)
        if not wanted:
            raise ValueError("Catégorie vide : précisez la catégorie de la dépense ou du revenu.")
        allowed = None if among is None else {normalize(name) for name in among}

        def candidate(name: str) -> bool:
            return allowed is None or normalize(name) in allowed

        categories = {normalize(c.name): c.name for c in self.get_categories(active_only=True) if candidate(c.name)}
        if wanted in categories:
            return CategoryResolution(spoken=spoken, status="resolved", category=categories[wanted], source="category")

        padded = f" {wanted} "
        matches = sorted({
            rule.category for rule in self.get_auto_sort_rules()
            if candidate(rule.category)
            and (f" {normalize(rule.keyword)} " in padded or padded in f" {normalize(rule.keyword)} ")
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

    def group_members(self, name: str) -> List[str]:
        """Catégories du groupe `name` dans `Gestion` ; liste vide si `name` est une catégorie (elle l'emporte)."""
        return self._gestion_lines(self._values(GESTION_SHEET), name)[2]

    @staticmethod
    def _gestion_groups(rows: List[List[Any]]) -> Dict[int, List[int]]:
        """Groupes de `Gestion` (index de la ligne d'en-tête → index de ses catégories), après la 1re ligne vide."""
        first_blank = next((i for i, row in enumerate(rows) if _is_blank(_cell(row, 0))), len(rows))
        return _row_groups(rows, first_blank)

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

    # --- Écran Budget : vue d'ensemble (lecture seule) -------------------------------------------

    def get_overview(self) -> BudgetOverview:
        """Groupes et catégories de `Gestion` avec le suivi du mois actif, série Dépenses / Revenus et épargné.

        Budget du mois = Prévu + Equilibrage (Reste fin du mois = budget − dépensé dans le classeur) ; dépensé = ligne
        de la catégorie dans `Total dépenses`. Catégories terminées (`Catégories`) masquées, mais comptées dans le
        total de leur groupe, comme la ligne « Total » du classeur ; un groupe sans catégorie affichée est omis.
        """
        active = self.get_active_month()
        total = self._values(TOTAL_SHEET)
        gestion = self._values(GESTION_SHEET)
        self._check_total_lines(total)
        month_cols = self._total_month_cols(total)
        active_col = month_cols[active]

        def total_line(row: int, col: int, month: BudgetMonth) -> float:
            where = f"« {TOTAL_SHEET} », {TOTAL_LINE_LABELS[row]} de {month.label}"
            return self._optional_amount(_cell(_cell(total, row) or [], col), where)

        series = [
            MonthlyTotals(month=month, expenses=total_line(TOTAL_EXPENSES_ROW, col, month),
                          income=total_line(TOTAL_INCOME_ROW, col, month))
            for month, col in month_cols.items() if month.year == active.year and month.month <= active.month
        ]
        spent_rows = _rows_by_name(total, _row_groups(total, TOTAL_FIRST_GROUP_ROW))
        today = self._today()
        ended = {normalize(c.name) for c in self.get_categories() if not c.is_active(today)}
        col = self._gestion_month_col(gestion, active)
        groups = []
        for header, members in self._gestion_groups(gestion).items():
            lines, group_total = [], 0.0
            for index in members:
                row = gestion[index]
                name = str(row[0]).strip()
                where = f"« {GESTION_SHEET} », {name}"
                group_total += self._amount(_cell(row, GESTION_REMAINING_COL), f"{where}, colonne B")
                if normalize(name) in ended:
                    continue
                spent_row = _single_row(total, spent_rows, name, TOTAL_SHEET)
                lines.append(BudgetCategoryLine(
                    name=name,
                    total_remaining=self._amount(_cell(row, GESTION_REMAINING_COL), f"{where}, colonne B"),
                    month_spent=self._optional_amount(
                        _cell(total[spent_row], active_col), f"« {TOTAL_SHEET} », {name}, {active.label}"),
                    month_budget=round(
                        self._optional_amount(_cell(row, col), f"{where}, Prévu de {active.label}")
                        + self._optional_amount(_cell(row, col + 1), f"{where}, Equilibrage de {active.label}"), 2,
                    ) + 0.0,
                ))
            if lines:
                name = str(gestion[header][0]).strip()
                groups.append(BudgetGroup(
                    name=name, kind="income" if normalize(name) == normalize(INCOME_GROUP) else "expense",
                    total_remaining=round(group_total, 2) + 0.0, categories=lines,
                ))
        return BudgetOverview(
            active_month=active, saved=total_line(TOTAL_SAVED_ROW, active_col, active), series=series, groups=groups,
        )

    @staticmethod
    def _check_total_lines(rows: List[List[Any]]) -> None:
        for row, label in TOTAL_LINE_LABELS.items():
            found = _cell(_cell(rows, row) or [], 0)
            if normalize(found) != normalize(label):
                raise BudgetHeaderError(
                    f"« {label} » attendu en ligne {row + 1} (colonne A) de « {TOTAL_SHEET} », trouvé {found!r} : "
                    "la structure de l'onglet a changé."
                )

    def _total_month_cols(self, rows: List[List[Any]]) -> Dict[BudgetMonth, int]:
        """Colonnes des mois de `Total dépenses` (ligne 2, numéros de série à partir de D), dans l'ordre."""
        months = _cell(rows, TOTAL_MONTHS_ROW) or []
        return {
            self._month(months[col], f"« {TOTAL_SHEET} » ligne 2, colonne {col + 1}"): col
            for col in range(TOTAL_FIRST_MONTH_COL, len(months)) if _is_number(months[col])
        }

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

    # --- Écritures : saisies, échéanciers, dépenses multiples ------------------------------------

    def add_entry(self, entry: BudgetEntry) -> int:
        """Dépense, remboursement ou revenu ; renvoie le numéro de la ligne écrite (1-indexé)."""
        return self._append(entry)

    def add_installment(self, installment: NewInstallment) -> int:
        """Échéancier au format de `createInstallment` ; renvoie le numéro de la ligne écrite (1-indexé)."""
        return self._append(installment)

    def add_split_expense(self, split: SplitExpense) -> int:
        """Dépense multiple au format de `createSplitTransaction` ; renvoie le numéro de la ligne écrite (1-indexé)."""
        return self._append(split)

    def _append(self, record: WrittenRow) -> int:
        """Écrit la ligne à la première ligne vide de son onglet (relu à neuf), puis ses formats de nombre."""
        sheet = _sheet_of(record)
        rows = self._fresh_table(sheet)
        row = len(rows) + 2  # en-tête + données : comme getLastRow() + 1
        worksheet = self._worksheet(sheet)
        if worksheet.row_count < row:
            worksheet.add_rows(row - worksheet.row_count)  # onglet plein (Revenus, Échéanciers) : grille agrandie
        cells = [value.isoformat() if isinstance(value, date) else value for value in _cells(record)]
        worksheet.update(
            range_name=f"A{row}:{chr(ord('A') + len(cells) - 1)}{row}", values=[cells], value_input_option="USER_ENTERED",
        )
        formats = [{"range": f"{col}{row}", "format": fmt} for col, fmt in _FORMATS.get(sheet, ())]
        if formats:
            worksheet.batch_format(formats)
        self._invalidate_after_write(sheet)
        return row

    def delete_entry(self, record: WrittenRow) -> None:
        """Supprime la ligne écrite par Otis, seulement si elle est restée identique."""
        row = self.require_entry_row(record)
        sheet = _sheet_of(record)
        self._worksheet(sheet).delete_rows(row)
        self._invalidate_after_write(sheet)

    def set_entry_category(self, entry: BudgetEntry, category: str) -> BudgetEntry:
        """Change la catégorie (colonne Type) de la ligne écrite par Otis, seulement si elle est restée identique."""
        row = self.require_entry_row(entry)
        self._worksheet(entry.sheet).update(
            range_name=f"{ENTRY_CATEGORY_COL}{row}", values=[[category]], value_input_option="USER_ENTERED",
        )
        self._invalidate_after_write(entry.sheet)
        return entry.model_copy(update={"category": category})

    def _fresh_table(self, title: str) -> List[List[Any]]:
        """Lignes de données relues à neuf : jamais d'écriture sur la foi d'un cache (l'import a pu ajouter des lignes)."""
        self.invalidate_cache(title)
        return self._table(title)

    def require_entry_row(self, record: WrittenRow) -> int:
        """Numéro (1-indexé) de la dernière ligne identique à `record`, sinon erreur « supprimée ou modifiée depuis »."""
        expected = _cells(record)
        sheet = _sheet_of(record)
        rows = self._fresh_table(sheet)
        for index in range(len(rows) - 1, -1, -1):  # la plus récente d'abord (deux dépenses identiques dictées)
            if _same_row(rows[index], expected):
                return index + 2
        raise BudgetEntryChangedError(f"{_describe(record)} dans « {sheet} » : je n'y touche pas.")

    def _invalidate_after_write(self, title: str) -> None:
        self.invalidate_cache(title)
        self.invalidate_cache(GESTION_SHEET)


def _row_groups(rows: List[List[Any]], start: int) -> Dict[int, List[int]]:
    """Groupes à partir de la ligne `start` (index 0) : en-tête = 1re ligne non vide (au début ou après une ligne
    vide), puis ses catégories jusqu'à une ligne « Total… » (« Total », « Total: », « Total revenus »).

    Seul un bloc fermé par sa ligne « Total… » et non vide est un groupe : le bas de `Gestion` porte des blocs de
    synthèse (« Reste pour équilibrage (base) », « Déjà réinjecté »…) qui n'en sont pas.
    """
    groups: Dict[int, List[int]] = {}
    current: Optional[int] = None
    members: List[int] = []
    for index in range(start, len(rows)):
        label = _cell(rows[index], 0)
        if _is_blank(label):
            current = None
        elif current is None:
            current, members = index, []
        elif normalize(label).startswith("total"):
            if members:
                groups[current] = members
            current = None
        else:
            members.append(index)
    return groups


def _rows_by_name(rows: List[List[Any]], groups: Dict[int, List[int]]) -> Dict[str, List[int]]:
    """Index des lignes de catégorie par nom normalisé (un nom en double est refusé à la lecture)."""
    found: Dict[str, List[int]] = {}
    for members in groups.values():
        for index in members:
            found.setdefault(normalize(rows[index][0]), []).append(index)
    return found


def _single_row(table: List[List[Any]], rows_by_name: Dict[str, List[int]], name: str, sheet: str) -> int:
    rows = rows_by_name.get(normalize(name), [])
    if len(rows) > 1:
        raise BudgetCategoryNotFoundError(
            f"Catégorie « {name} » présente {len(rows)} fois dans « {sheet} » (lignes {[i + 1 for i in rows]}) : "
            "impossible de choisir."
        )
    if not rows:
        raise BudgetCategoryNotFoundError(
            f"Catégorie « {name} » introuvable dans « {sheet} ». Catégories disponibles : "
            f"{[str(table[i][0]).strip() for found in rows_by_name.values() for i in found]}"
        )
    return rows[0]


_FORMATS: Dict[str, Tuple[Tuple[str, Dict[str, Any]], ...]] = {
    INSTALLMENTS_SHEET: (("B", CURRENCY_FORMAT), ("E", CURRENCY_FORMAT), ("F", MONTH_FORMAT)),
    SPLITS_SHEET: (("A", DAY_FORMAT), ("C", CURRENCY_FORMAT)),
}


def _sheet_of(record: WrittenRow) -> str:
    if isinstance(record, NewInstallment):
        return INSTALLMENTS_SHEET
    if isinstance(record, SplitExpense):
        return SPLITS_SHEET
    return record.sheet


def _cells(record: WrittenRow) -> List[Any]:
    """Cellules A→ de la ligne, dates en `date` (écrites en ISO : comprises par Sheets quelle que soit la langue).

    Saisie : date, montant, catégorie, commentaire vide et intitulé (Swile n'a pas de colonne Intitulé : l'intitulé va
    dans Commentaires). Échéancier et dépense multiple : colonnes de `createInstallment` / `createSplitTransaction`,
    le mois de début étant stocké en date du 1er du mois, comme le fait l'`appendRow` de l'Apps Script.
    """
    if isinstance(record, NewInstallment):
        start = date(record.start_month.year, record.start_month.month, 1)
        return [
            record.name, record.total_amount, record.count, 0, record.monthly_amount, start, record.category,
            record.comment, INSTALLMENT_ACTIVE,
        ]
    if isinstance(record, SplitExpense):
        return [
            record.day, record.keyword, record.total_amount, SPLIT_TO_PROCESS, record.description, record.parts_json,
        ]
    head: List[Any] = [record.day, record.amount, record.category]
    if record.sheet == SWILE_SHEET:
        return head + [record.label]
    return head + ["", record.label]


def _describe(record: WrittenRow) -> str:
    if isinstance(record, NewInstallment):
        return (
            f"L'échéancier « {record.name} » ({record.total_amount:g} € en {record.count} fois) a été supprimé ou "
            "modifié depuis (une échéance a peut-être déjà été rapprochée par l'import)"
        )
    if isinstance(record, SplitExpense):
        return (
            f"La dépense multiple « {record.keyword} » ({record.total_amount:g} € vers le {record.day:%d/%m/%Y}) a été "
            "supprimée, modifiée ou déjà traitée par l'import depuis"
        )
    return (
        f"La ligne « {record.label} » ({record.amount:g} € en {record.category.strip()} le {record.day:%d/%m/%Y}) "
        "a été supprimée ou modifiée depuis"
    )


def _same_row(row: Sequence[Any], expected: Sequence[Any]) -> bool:
    """Ligne relue (valeurs brutes) identique aux cellules écrites : date = numéro de série, montant au centime,
    texte aux espaces de bord près."""
    for index, wanted in enumerate(expected):
        found = _cell(row, index)
        if isinstance(wanted, date):
            if found != (wanted - SHEETS_EPOCH).days:
                return False
        elif _is_number(wanted):
            if not _is_number(found) or round(float(found), 2) != round(float(wanted), 2):
                return False
        elif str(found).strip() != str(wanted).strip():
            return False
    return True
