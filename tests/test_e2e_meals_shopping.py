"""Test d'intégration End-to-End (E2E) pour le connecteur repas, recettes et courses.

Par défaut, tous les tests s'exécutent sur un classeur in-memory mocké ultra-réaliste
pour garantir ZÉRO effet de bord et ZÉRO pollution sur le Google Sheet réel de l'utilisateur.
"""
from datetime import date, datetime, timedelta
import os
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app, set_meals_connector
from app.connectors.sheets.meals_connector import MealsShoppingConnector

client = TestClient(app)


def _build_in_memory_spreadsheet():
    """Construit un mock complet de Google Sheets contenant toutes les feuilles requises."""
    sh = MagicMock()
    worksheets = {}

    today_str = date.today().strftime("%d/%m/%Y")
    current_year = date.today().year

    # 1. Feuille repas annuelle (ex: repas 2026)
    repas_data = [
        ["Date", "Jour", "Midi", "Soir", "Notes / Magasin"],
        [today_str, "Vendredi", "Salade composée", "Risotto de quinoa", ""],
    ]
    ws_repas = MagicMock()
    ws_repas.title = f"repas {current_year}"
    ws_repas.get_all_values.return_value = repas_data
    worksheets[f"repas {current_year}"] = ws_repas

    # 2. Recettes standard
    recettes_data = [
        ["Plat", "Catégorie", "Catégorie 2", "Complet", "Ingrédient", "", "", ""],
        ["Risotto de quinoa", "Féculents", "Chaud", "TRUE", "Quinoa", "Courgette", "Bouillon", "Parmesan"],
    ]
    ws_recettes = MagicMock()
    ws_recettes.title = "Recettes"
    ws_recettes.get_all_values.return_value = recettes_data
    worksheets["Recettes"] = ws_recettes

    # 3. Recettes festives
    festive_data = [
        ["Plat", "Catégorie", "Catégorie 2", "Complet", "Ingrédient", "", "", ""],
        ["Guacamole", "Apéro", "Froid", "FALSE", "Avocat", "Citron vert", "Épices", ""],
    ]
    ws_festive = MagicMock()
    ws_festive.title = "Recette festive"
    ws_festive.get_all_values.return_value = festive_data
    worksheets["Recette festive"] = ws_festive

    # 4. Rayons
    rayons_data = [
        ["Rayon", "Ordre"],
        ["Fruits & Légumes", "1"],
        ["Épicerie", "2"],
        ["Frais", "3"],
        ["Divers", "99"],
    ]
    ws_rayons = MagicMock()
    ws_rayons.title = "Rayons"
    ws_rayons.get_all_values.return_value = rayons_data
    worksheets["Rayons"] = ws_rayons

    # 5. Cette semaine
    cette_semaine_data = [
        ["Acheté", "Article", "Rayon"],
        ["FALSE", "Quinoa", "Épicerie"],
        ["TRUE", "Courgette", "Fruits & Légumes"],
    ]
    ws_cette_semaine = MagicMock()
    ws_cette_semaine.title = "Cette semaine"
    ws_cette_semaine.get_all_values.return_value = cette_semaine_data
    worksheets["Cette semaine"] = ws_cette_semaine

    # 6. Liste_Attente dynamique in-memory
    liste_attente_state = [
        ["Acheté", "Article", "Date d'ajout"],
    ]
    ws_attente = MagicMock()
    ws_attente.title = "Liste_Attente"

    def get_attente_values():
        return [[str(c) for c in r] for r in liste_attente_state]

    ws_attente.get_all_values.side_effect = get_attente_values

    def append_attente_row(row, *args, **kwargs):
        liste_attente_state.append(list(row))

    def append_attente_rows(rows, *args, **kwargs):
        for r in rows:
            liste_attente_state.append(list(r))

    ws_attente.append_row.side_effect = append_attente_row
    ws_attente.append_rows.side_effect = append_attente_rows

    def update_cell(row_idx, col_idx, value):
        if row_idx <= len(liste_attente_state):
            while len(liste_attente_state[row_idx - 1]) < col_idx:
                liste_attente_state[row_idx - 1].append("")
            liste_attente_state[row_idx - 1][col_idx - 1] = str(value)

    ws_attente.update_cell.side_effect = update_cell

    def delete_rows(row_idx):
        if 0 < row_idx <= len(liste_attente_state):
            liste_attente_state.pop(row_idx - 1)

    ws_attente.delete_rows.side_effect = delete_rows

    worksheets["Liste_Attente"] = ws_attente

    sh.worksheets.return_value = list(worksheets.values())
    sh.worksheet.side_effect = lambda name: worksheets[name]

    return sh


@pytest.fixture
def isolated_e2e_connector():
    """Initialise un MealsShoppingConnector avec un Google Sheet mocké 100% in-memory."""
    sh = _build_in_memory_spreadsheet()
    connector = MealsShoppingConnector(spreadsheet=sh)
    set_meals_connector(connector)
    yield connector
    set_meals_connector(None)


def test_e2e_get_recipe_ingredients_flow(isolated_e2e_connector):
    """Valide la chaîne complète NLU -> Recherche Recette -> Réponse vocale en isolation totale."""
    response = client.post(
        "/api/v1/interact",
        json={"query": "Quels sont les ingrédients pour le risotto de quinoa ?"},
    )
    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["intent"]["intent"] == "get_recipe_ingredients"
    assert "risotto de quinoa" in data["spoken_response"].lower()
    assert "quinoa" in data["spoken_response"].lower()
    assert "courgette" in data["spoken_response"].lower()
    assert "recipe" in data["data"]
    assert "Quinoa" in data["data"]["recipe"]["ingredients"]


def test_e2e_get_festive_recipe_ingredients_flow(isolated_e2e_connector):
    """Valide la recherche dans l'onglet Recette festive en isolation."""
    response = client.post(
        "/api/v1/interact",
        json={"query": "Qu'est-ce qu'il faut pour faire du guacamole ?"},
    )
    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["intent"]["intent"] == "get_recipe_ingredients"
    assert "guacamole" in data["spoken_response"].lower()
    assert "avocat" in data["spoken_response"].lower()


def test_e2e_get_shopping_list_flow(isolated_e2e_connector):
    """Valide la consultation de la liste de courses en isolation."""
    response = client.post(
        "/api/v1/interact",
        json={"query": "Donne-moi la liste de courses"},
    )
    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["intent"]["intent"] == "get_shopping_list"
    assert "shopping_list" in data["data"]
    assert "waiting_list" in data["data"]["shopping_list"]
    assert "current_week_items" in data["data"]["shopping_list"]


def test_e2e_shopping_item_lifecycle_flow(isolated_e2e_connector):
    """Valide le cycle de vie complet d'un article sans JAMAIS polluer le Google Sheet réel :
    
    1. Ajout dans Liste_Attente
    2. Marquage comme acheté
    3. Nettoyage de la liste (suppression propre)
    """
    timestamp = int(datetime.now().timestamp())
    test_item = f"Café test E2E {timestamp}"

    # 1. Ajout
    r1 = client.post(
        "/api/v1/interact",
        json={"query": f"Ajoute {test_item} à la liste de courses"},
    )
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["success"] is True
    assert test_item.lower() in d1["spoken_response"].lower()

    # Vérification que la ligne est présente dans Liste_Attente in-memory
    ws = isolated_e2e_connector.spreadsheet.worksheet("Liste_Attente")
    records = ws.get_all_values()
    added_row = next((row for row in records if len(row) > 1 and row[1].strip().lower() == test_item.lower()), None)
    assert added_row is not None
    assert added_row[0].upper() == "FALSE"

    # 2. Marquage acheté
    r2 = client.post(
        "/api/v1/interact",
        json={"query": f"J'ai acheté {test_item}"},
    )
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["success"] is True

    # Vérification que la case est devenue TRUE in-memory
    records_after_buy = ws.get_all_values()
    bought_row = next((row for row in records_after_buy if len(row) > 1 and row[1].strip().lower() == test_item.lower()), None)
    assert bought_row is not None
    assert bought_row[0].upper() == "TRUE"

    # 3. Nettoyage
    r3 = client.post(
        "/api/v1/interact",
        json={"query": "Vide la liste de courses"},
    )
    assert r3.status_code == 200
    d3 = r3.json()
    assert d3["success"] is True

    # Vérification que l'article temporaire a bien été supprimé in-memory
    records_after_clear = ws.get_all_values()
    cleaned_row = next((row for row in records_after_clear if len(row) > 1 and row[1].strip().lower() == test_item.lower()), None)
    assert cleaned_row is None
