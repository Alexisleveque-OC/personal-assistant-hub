"""Console interactive pour tester et converser avec Personal Assistant Hub."""
import asyncio
import sys
from pathlib import Path

# Ajouter la racine du projet au sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.models import InteractionRequest
from app.main import interact, get_meals_connector


def print_banner():
    print("\n" + "=" * 65)
    print(" 🤖 PERSONAL ASSISTANT HUB - CONSOLE INTERACTIVE DE TEST")
    print("=" * 65)
    print("Vous pouvez tester des commandes naturelles en français :")
    print("  • Qu'est-ce qu'on mange ce soir ?")
    print("  • Quels sont les ingrédients pour le risotto de quinoa ?")
    print("  • Qu'est-ce qu'il faut pour faire du guacamole ?")
    print("  • Ajoute du café bio à la liste de courses")
    print("  • Donne-moi la liste de courses")
    print("  • J'ai acheté le café bio")
    print("  • Vide la liste de courses")
    print("Tapez 'exit' ou 'quit' pour quitter.")
    print("=" * 65 + "\n")


async def chat_loop():
    print_banner()

    # Initialisation / vérification de la connexion Google Sheet
    print("⏳ Vérification de la connexion Google Sheets...")
    connector = get_meals_connector()
    if connector and await connector.is_healthy():
        print(f"✅ Connecté au tableur : '{connector.spreadsheet.title}'\n")
    else:
        print("⚠️ Mode hors-ligne / Connecteur réel non initialisé (réponses de simulation actives)\n")

    while True:
        try:
            query = input("Vous > ").strip()
            if not query:
                continue
            if query.lower() in ["exit", "quit", "q"]:
                print("\nAu revoir ! 👋\n")
                break

            request = InteractionRequest(query=query, source="cli")
            response = await interact(request)

            print(f"\nAssistant > {response.spoken_response}")
            print(f"         [Intention: {response.intent.intent.value} | Confiance: {response.intent.confidence * 100:.0f}%]")

            # Détails complémentaires si pertinents
            if "recipe" in response.data and response.data["recipe"]:
                rec = response.data["recipe"]
                print(f"         📖 Recette: {rec.get('name')} ({len(rec.get('ingredients', []))} ingrédients)")
            if "item" in response.data and response.data["item"]:
                it = response.data["item"]
                print(f"         🛒 Article: {it.get('item')} (Rayon déduit: {it.get('rayon')})")

            print()

        except (KeyboardInterrupt, EOFError):
            print("\n\nFermeture de la session. À bientôt ! 👋")
            break
        except Exception as err:
            print(f"\n❌ Erreur : {err}\n")


if __name__ == "__main__":
    asyncio.run(chat_loop())
