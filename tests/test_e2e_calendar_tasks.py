"""E2E Phase 8 (Étape 6) : Agenda et Tâches de bout en bout, de la voix à l'onglet « Tâches » de la PWA.

Phrase → /interact → agent (LLM scripté) → outils → VRAIS `CalendarConnector` / `TasksConnector` → requêtes REST
Google (seul le réseau est simulé, par une API en mémoire) → réponse ; puis l'onglet Tâches lit et coche la même
liste via `/api/v1/tasks`. Vérifie au passage le cache partagé et son invalidation à chaque écriture.
"""
from datetime import date, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.connectors.calendar.calendar_connector import CALENDAR_API, CalendarConnector
from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.connectors.tasks.tasks_connector import TasksConnector
from app.core.agent.factory import set_agent_llm
from app.core.clock import paris_today
from app.core.dependencies import set_calendar_connector, set_sport_connector, set_tasks_connector
from app.core.session_manager import get_session_manager
from app.main import app
from tests.agent_fakes import ScriptedLLM, call_turn, text_turn

SESSION = "e2e-calendar-tasks"
TASKS_URL = "https://tasks.googleapis.com/tasks/v1/lists/@default/tasks"


class FakeResponse:
    def __init__(self, payload: Optional[Dict[str, Any]], status_code: int = 200) -> None:
        self._payload = payload or {}
        self.status_code = status_code
        self.text = str(payload)

    def json(self) -> Dict[str, Any]:
        return self._payload


class FakeGoogleApi:
    """Google Agenda (lecture) et Google Tasks (lecture/écriture) en mémoire, au niveau HTTP d'`AuthorizedSession`."""

    def __init__(self, events: List[Dict[str, Any]], tasks: List[Dict[str, Any]]) -> None:
        self.events = events
        self.tasks: Dict[str, Dict[str, Any]] = {t["id"]: t for t in tasks}
        self.calls: List[tuple] = []
        self._next_id = 1

    def get(self, url: str, params: Optional[Dict[str, Any]] = None) -> FakeResponse:
        self.calls.append(("GET", url))
        if url == f"{CALENDAR_API}/users/me/calendarList":
            return FakeResponse({"items": [{"id": "perso", "summary": "Perso", "selected": True}]})
        if url == f"{CALENDAR_API}/calendars/{quote('perso', safe='')}/events":
            return FakeResponse({"items": self.events})
        if url == TASKS_URL:
            return FakeResponse({"items": [t for t in self.tasks.values() if t["status"] != "completed"]})
        task_id = url.removeprefix(f"{TASKS_URL}/")
        return FakeResponse(self.tasks[task_id]) if task_id in self.tasks else FakeResponse({"error": "Not Found"}, 404)

    def request(self, method: str, url: str, params=None, json: Optional[Dict[str, Any]] = None) -> FakeResponse:
        self.calls.append((method, url))
        if method == "POST" and url == TASKS_URL:
            task = {"id": f"new{self._next_id}", "status": "needsAction", **(json or {})}
            self._next_id += 1
            self.tasks[task["id"]] = task
            return FakeResponse(task)
        task_id = url.removeprefix(f"{TASKS_URL}/")
        if task_id not in self.tasks:
            return FakeResponse({"error": "Not Found"}, 404)
        if method == "PATCH":
            self.tasks[task_id] = {k: v for k, v in {**self.tasks[task_id], **(json or {})}.items() if v is not None}
            return FakeResponse(self.tasks[task_id])
        if method == "DELETE":
            del self.tasks[task_id]
            return FakeResponse(None, 204)
        raise AssertionError(f"Appel Google inattendu : {method} {url}")

    def reads_of(self, url: str) -> int:
        return sum(1 for call in self.calls if call == ("GET", url))


@pytest.fixture
def env(isolate_sqlite_database, monkeypatch):
    monkeypatch.setattr(settings, "nlu_mode", "agent")
    today = paris_today()
    google = FakeGoogleApi(
        events=[{
            "summary": "Dentiste",
            "start": {"dateTime": f"{(today + timedelta(days=1)).isoformat()}T09:30:00+01:00"},
            "end": {"dateTime": f"{(today + timedelta(days=1)).isoformat()}T10:00:00+01:00"},
        }],
        tasks=[{
            "id": "cantine", "title": "Payer la cantine", "status": "needsAction",
            "due": f"{(today - timedelta(days=1)).isoformat()}T00:00:00.000Z",
        }],
    )
    set_sport_connector(SqlSportConnector(db_manager=isolate_sqlite_database))
    set_calendar_connector(CalendarConnector(google))
    set_tasks_connector(TasksConnector(google))
    yield google, today
    get_session_manager().clear_all()
    set_sport_connector(None)
    set_agent_llm(None)


def _ask(client: TestClient, query: str) -> str:
    resp = client.post("/api/v1/interact", json={"query": query, "session_id": SESSION})
    assert resp.status_code == 200, resp.text
    return resp.json()["spoken_response"]


def _open_titles(client: TestClient) -> List[str]:
    resp = client.get("/api/v1/tasks")
    assert resp.status_code == 200, resp.text
    return [t["titre"] for t in resp.json()["taches"]]


def test_week_overview_then_voice_task_then_pwa_tab_then_undo(env):
    google, today = env
    friday_like = today + timedelta(days=3)
    llm = ScriptedLLM([
        # 1. « Cette semaine » : agenda ET tâches à échéance (règle 16 du prompt), lus par les vrais connecteurs.
        call_turn(
            {"name": "get_agenda", "args": {"date_debut": today.isoformat(), "date_fin": (today + timedelta(days=6)).isoformat()}},
            {"name": "get_tasks", "args": {}},
        ),
        text_turn("Demain dentiste à 9 h 30, et la cantine est en retard."),
        # 2. Tâche dictée : écrite dans Google Tasks avec son échéance.
        call_turn({"name": "add_task", "args": {"titre": "Envoyer les documents", "echeance": friday_like.isoformat()}}),
        text_turn("C'est ajouté à tes tâches."),
    ])
    set_agent_llm(llm)
    client = TestClient(app)

    # 1. Vue de la semaine
    assert _ask(client, "Qu'est-ce que j'ai cette semaine ?") == "Demain dentiste à 9 h 30, et la cantine est en retard."
    tool_results = str(llm.requests[1]["contents"])
    assert "Dentiste" in tool_results and "Payer la cantine" in tool_results
    assert "'en_retard': True" in tool_results

    # 2. Ajout à la voix : vraie requête POST Google, échéance au format jour seul
    assert _ask(client, "Rappelle-moi d'envoyer les documents dans trois jours") == "C'est ajouté à tes tâches."
    created = google.tasks["new1"]
    assert (created["title"], created["due"]) == ("Envoyer les documents", f"{friday_like.isoformat()}T00:00:00.000Z")

    # 3. Onglet Tâches : même connecteur, cache invalidé par l'écriture vocale → la nouvelle tâche est là
    assert _open_titles(client) == ["Payer la cantine", "Envoyer les documents"]
    reads = google.reads_of(TASKS_URL)
    assert _open_titles(client) == ["Payer la cantine", "Envoyer les documents"]
    assert google.reads_of(TASKS_URL) == reads  # 2e ouverture servie par le cache (règle 8)

    # 4. Cocher dans l'onglet, puis « Annuler » : la tâche disparaît puis revient, sans date de complétion
    assert client.patch("/api/v1/tasks/cantine", json={"terminee": True}).status_code == 200
    assert google.tasks["cantine"]["status"] == "completed"
    assert _open_titles(client) == ["Envoyer les documents"]
    assert client.patch("/api/v1/tasks/cantine", json={"terminee": False}).status_code == 200
    assert google.tasks["cantine"]["status"] == "needsAction" and "completed" not in google.tasks["cantine"]
    assert _open_titles(client) == ["Payer la cantine", "Envoyer les documents"]

    # 5. « Annule ça » à la voix : la tâche ajoutée par l'assistant est supprimée de Google, l'onglet le reflète
    assert "tâche « Envoyer les documents » supprimée" in _ask(client, "annule ça")
    assert "new1" not in google.tasks
    assert _open_titles(client) == ["Payer la cantine"]


def test_pwa_tab_adds_a_task_that_the_assistant_then_reads(env):
    google, today = env
    llm = ScriptedLLM([call_turn({"name": "get_tasks", "args": {}}), text_turn("Deux tâches.")])
    set_agent_llm(llm)
    client = TestClient(app)

    resp = client.post("/api/v1/tasks", json={"titre": "Acheter des ampoules"})
    assert resp.status_code == 201, resp.text
    assert google.tasks["new1"]["title"] == "Acheter des ampoules" and "due" not in google.tasks["new1"]

    assert _ask(client, "Liste-moi mes tâches") == "Deux tâches."
    assert "Acheter des ampoules" in str(llm.requests[1]["contents"])
