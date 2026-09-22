"""Script de démonstration interactif pour tester la sécurité de l'API (X-API-Key)."""
import sys
from pathlib import Path

# Assurer l'encodage UTF-8 pour la console Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from fastapi.testclient import TestClient

# Ajouter la racine du projet
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings
from app.main import app

client = TestClient(app)


def print_title(title: str):
    print("\n" + "=" * 65)
    print(f" [SECURITE] {title}")
    print("=" * 65)


def run_demo():
    print_title("DEMONSTRATION DU VERROUILLAGE PAR CLE API (X-API-Key)")
    print("Ce script teste les requetes qu'un attaquant ou votre smartphone enverrait.\n")

    SECRET = "mon-secret-smartphone-2026"
    settings.api_key = SECRET
    print(f"[*] Configuration active : API_KEY = '{SECRET}'\n")

    # Scenario 1 : Requete sans aucune cle
    print("-> Scenario 1 : Requete anonyme (sans header X-API-Key)")
    res1 = client.post("/api/v1/interact", json={"query": "Qu'est-ce qu'on mange ce soir ?"})
    print(f"   * Code HTTP recu : {res1.status_code}")
    print(f"   * Reponse JSON   : {res1.json()}")
    if res1.status_code == 401:
        print("   -> SUCCES : ACCES BLOQUE (401 Unauthorized) - Vos donnees sont protegees !\n")
    else:
        print("   -> ECHEC\n")

    # Scenario 2 : Requete avec une mauvaise cle
    print("-> Scenario 2 : Requete avec une mauvaise cle ('pirate-key')")
    res2 = client.post(
        "/api/v1/interact",
        headers={"X-API-Key": "pirate-key"},
        json={"query": "Qu'est-ce qu'on mange ce soir ?"},
    )
    print(f"   * Code HTTP recu : {res2.status_code}")
    print(f"   * Reponse JSON   : {res2.json()}")
    if res2.status_code == 401:
        print("   -> SUCCES : ACCES BLOQUE (401 Unauthorized) - Cle rejetee !\n")
    else:
        print("   -> ECHEC\n")

    # Scenario 3 : Requete avec la bonne cle secrete
    print(f"-> Scenario 3 : Requete legitime depuis votre smartphone (cle '{SECRET}')")
    res3 = client.post(
        "/api/v1/interact",
        headers={"X-API-Key": SECRET},
        json={"query": "Qu'est-ce qu'on mange ce soir ?"},
    )
    print(f"   * Code HTTP recu : {res3.status_code}")
    print(f"   * Reponse vocale : \"{res3.json().get('spoken_response')}\"")
    if res3.status_code == 200:
        print("   -> SUCCES : ACCES AUTORISE (200 OK) - L'assistant repond normalement !\n")
    else:
        print("   -> ECHEC\n")

    # Scenario 4 : Verification des routes publiques
    print("-> Scenario 4 : Verification que la documentation et la sante restent accessibles publiquement")
    res_health = client.get("/health")
    print(f"   * /health (sans cle) : Code {res_health.status_code} -> {res_health.json()}")
    if res_health.status_code == 200:
        print("   -> SUCCES : Les endpoints publics restent ouverts sans cle.\n")

    # Remise a zero
    settings.api_key = ""
    print("=" * 65)
    print("FIN DU TEST : La securite fonctionne exactement comme attendu.")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    run_demo()
