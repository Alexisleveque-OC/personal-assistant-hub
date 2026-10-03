"""Tests de dialogue multi-tours et clarifications naturelles pour les courses (Étape 3)."""
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from app.main import app, set_meals_connector
from app.connectors.sheets.models import WaitingListItem

client = TestClient(app)


def test_add_shopping_item_known_rayon_adds_immediately():
    """Un article dont le rayon est connu est ajouté immédiatement sans clarification."""
    mock_connector = MagicMock()
    mock_connector.resolve_rayon.return_value = ("Frais", None)
    mock_connector.add_shopping_item.return_value = (
        WaitingListItem(item="Lait", rayon="Frais"),
        None,
    )
    set_meals_connector(mock_connector)

    res = client.post(
        "/api/v1/interact",
        json={"query": "Ajoute du lait", "source": "session_test_known"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "lait" in data["spoken_response"].lower()
    assert "pending_action" not in data.get("data", {})
    mock_connector.add_shopping_item.assert_called_once()

    set_meals_connector(None)


def test_add_shopping_item_unknown_rayon_triggers_clarification():
    """Un article dont le rayon est inconnu déclenche une question de clarification naturelle."""
    mock_connector = MagicMock()
    mock_connector.resolve_rayon.return_value = (
        "Divers",
        "Rayon non répertorié pour 'Papier cuisson', classé temporairement en 'Divers'.",
    )
    mock_connector.suggest_rayons_for_item.return_value = ["Entretien", "Épicerie"]
    set_meals_connector(mock_connector)

    # 1. Requête initiale
    res = client.post(
        "/api/v1/interact",
        json={"query": "Ajoute du papier cuisson", "source": "session_clarif_1"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    # Ne doit pas encore avoir ajouté dans le connecteur
    mock_connector.add_shopping_item.assert_not_called()
    assert "papier cuisson" in data["spoken_response"].lower()
    assert "entretien" in data["spoken_response"].lower()
    assert "épicerie" in data["spoken_response"].lower()
    assert data["data"].get("pending_action", {}).get("type") == "clarify_shopping_rayon"

    set_meals_connector(None)


def test_clarification_choice_en_entretien_adds_item_with_chosen_rayon():
    """Tour 2 : L'utilisateur répond 'En entretien' et l'article est ajouté dans le bon rayon."""
    mock_connector = MagicMock()
    mock_connector.resolve_rayon.return_value = (
        "Divers",
        "Rayon non répertorié pour 'Papier cuisson', classé temporairement en 'Divers'.",
    )
    mock_connector.suggest_rayons_for_item.return_value = ["Entretien", "Épicerie"]
    mock_connector.add_shopping_item.return_value = (
        WaitingListItem(item="Papier cuisson", rayon="Entretien"),
        None,
    )
    set_meals_connector(mock_connector)

    # 1. Demande d'ajout
    r1 = client.post(
        "/api/v1/interact",
        json={"query": "Ajoute du papier cuisson", "source": "session_clarif_2"},
    )
    assert r1.status_code == 200
    assert "pending_action" in r1.json()["data"]

    # 2. Réponse de clarification
    r2 = client.post(
        "/api/v1/interact",
        json={"query": "En entretien", "source": "session_clarif_2"},
    )
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["success"] is True
    assert "entretien" in d2["spoken_response"].lower()
    assert "papier cuisson" in d2["spoken_response"].lower()
    # Le connecteur a été appelé avec le rayon choisi
    mock_connector.add_shopping_item.assert_called_once_with("Papier cuisson", rayon="Entretien")

    set_meals_connector(None)


def test_clarification_choice_laisse_en_divers():
    """Tour 2 : L'utilisateur répond 'Laisse en divers'."""
    mock_connector = MagicMock()
    mock_connector.resolve_rayon.return_value = (
        "Divers",
        "Rayon non répertorié pour 'Papier alu', classé temporairement en 'Divers'.",
    )
    mock_connector.suggest_rayons_for_item.return_value = ["Entretien", "Épicerie"]
    mock_connector.add_shopping_item.return_value = (
        WaitingListItem(item="Papier alu", rayon="Divers"),
        None,
    )
    set_meals_connector(mock_connector)

    # 1. Demande d'ajout
    client.post(
        "/api/v1/interact",
        json={"query": "Ajoute du papier alu", "source": "session_clarif_3"},
    )

    # 2. Réponse 'laisse en divers'
    r2 = client.post(
        "/api/v1/interact",
        json={"query": "Laisse en divers", "source": "session_clarif_3"},
    )
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["success"] is True
    assert "divers" in d2["spoken_response"].lower()
    mock_connector.add_shopping_item.assert_called_once_with("Papier alu", rayon="Divers")

    set_meals_connector(None)


def test_clarification_cancellation():
    """Tour 2 : L'utilisateur répond 'Annuler' ou 'Non'."""
    mock_connector = MagicMock()
    mock_connector.resolve_rayon.return_value = (
        "Divers",
        "Rayon non répertorié pour 'Papier cuisson', classé temporairement en 'Divers'.",
    )
    mock_connector.suggest_rayons_for_item.return_value = ["Entretien", "Épicerie"]
    set_meals_connector(mock_connector)

    # 1. Demande d'ajout
    client.post(
        "/api/v1/interact",
        json={"query": "Ajoute du papier cuisson", "source": "session_clarif_4"},
    )

    # 2. Réponse d'annulation
    r2 = client.post(
        "/api/v1/interact",
        json={"query": "Non annule", "source": "session_clarif_4"},
    )
    assert r2.status_code == 200
    d2 = r2.json()
    assert "annulé" in d2["spoken_response"].lower()
    mock_connector.add_shopping_item.assert_not_called()

    set_meals_connector(None)
