"""Outils métier sport de l'agent : recherche, lecture et mutations par identifiant uniquement.

Contrairement au connecteur (qui fusionne par date pour le flux legacy), ces outils ne devinent rien :
création stricte, aucune valeur inventée, instantané avant chaque mutation pour l'annulation.
"""
from datetime import date
from typing import Callable, List

from app.connectors.sheets.sport_models import SportSessionStatus
from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.core.agent.tools.sport_models import (
    FindSessionsArgs,
    LogSessionArgs,
    MutationResult,
    PlanSessionArgs,
    SessionRow,
    SessionView,
    UndoSnapshot,
    UpdateSessionArgs,
)
from app.core.clock import paris_today


class SportToolError(Exception):
    """Erreur métier explicite renvoyée à l'agent (jamais masquée)."""


class SportSessionNotFoundError(SportToolError):
    def __init__(self, session_id: int) -> None:
        super().__init__(f"Séance introuvable : aucun enregistrement avec l'identifiant {session_id}.")
        self.session_id = session_id


class SportTools:
    def __init__(self, connector: SqlSportConnector, today: Callable[[], date] = paris_today) -> None:
        self.connector = connector
        self.db = connector.db
        self.today = today

    def find_sport_sessions(self, args: FindSessionsArgs) -> List[SessionView]:
        rows = self.db.get_sport_sessions(
            start_date=args.date_from,
            end_date=args.date_to,
            session_type=args.type_seance.value if args.type_seance else None,
            status=args.statut.value if args.statut else None,
            order_desc=True,
            limit=args.limit,
        )
        return [self._view(row) for row in rows]

    def get_sport_session(self, session_id: int) -> SessionView:
        return self._view(self._raw_row(session_id))

    def update_sport_session(self, args: UpdateSessionArgs) -> MutationResult:
        before = SessionRow.model_validate(self._raw_row(args.session_id))
        updated = self.connector.update_session_by_id(args.session_id, args.changes.model_dump(exclude_none=True))
        return MutationResult(
            session=SessionView.from_session(updated),
            undo=UndoSnapshot(action="updated", session_id=args.session_id, before=before),
        )

    def log_sport_session(self, args: LogSessionArgs) -> MutationResult:
        if args.date > self.today():
            raise SportToolError(
                f"Impossible d'enregistrer une séance réalisée dans le futur ({args.date}, aujourd'hui {self.today()}) : "
                "utiliser plan_sport_session."
            )
        return self._create(args.model_dump(mode="json"), SportSessionStatus.REALISE)

    def plan_sport_session(self, args: PlanSessionArgs) -> MutationResult:
        if args.date < self.today():
            raise SportToolError(
                f"Impossible de planifier une séance dans le passé ({args.date}, aujourd'hui {self.today()}) : "
                "utiliser log_sport_session."
            )
        return self._create(args.model_dump(mode="json"), SportSessionStatus.PLANIFIE)

    def undo_sport_mutation(self, snapshot: UndoSnapshot) -> None:
        current = self._raw_row(snapshot.session_id)
        if snapshot.action == "created":
            self.connector.delete_session(snapshot.session_id)
            return
        restored = snapshot.before.model_dump(exclude={"id"})
        self.db.update_sport_session(snapshot.session_id, restored)
        for day in {current["date"], restored["date"]}:
            self._refresh_week(date.fromisoformat(day))

    def _create(self, values: dict, statut: SportSessionStatus) -> MutationResult:
        remarques = values.pop("remarques", None) or ""
        session_id = self.db.add_sport_session({
            **{k: v for k, v in values.items() if v is not None},
            "statut": statut.value,
            "remarques": remarques,
            "notes": remarques,
        })
        self._refresh_week(date.fromisoformat(values["date"]))
        return MutationResult(
            session=self.get_sport_session(session_id),
            undo=UndoSnapshot(action="created", session_id=session_id),
        )

    def _refresh_week(self, day: date) -> None:
        # Même convention que le connecteur : semaine ISO + année civile.
        self.connector.get_weekly_summary(week_num=day.isocalendar()[1], year=day.year)

    def _raw_row(self, session_id: int) -> dict:
        row = self.db.get_sport_session_by_id(session_id)
        if row is None:
            raise SportSessionNotFoundError(session_id)
        return row

    def _view(self, row: dict) -> SessionView:
        return SessionView.from_session(self.connector._row_to_sport_session(row))
