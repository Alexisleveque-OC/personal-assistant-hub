"""Point d'entrée principal de l'API Personal Assistant Hub."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.models import (
    InteractionRequest,
    InteractionResponse,
    IntentType,
    ParsedIntent,
)
from app.core.intent_parser import IntentParser

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Hub d'assistant personnel connecté à Google Sheets, Google Tasks, Gmail et Domotique.",
)

# CORS pour autoriser l'accès depuis une PWA, un widget ou un frontend local
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

intent_parser = IntentParser()


@app.get("/", tags=["System"])
async def root():
    return {
        "app": settings.app_name,
        "version": "0.1.0",
        "status": "online",
        "docs": "/docs",
    }


@app.get("/health", tags=["System"])
async def health_check():
    return {
        "status": "healthy",
        "environment": settings.app_env,
        "debug": settings.debug,
    }


@app.post("/api/v1/intent/parse", response_model=ParsedIntent, tags=["NLU"])
async def parse_intent(request: InteractionRequest):
    """Analyse la phrase en langage naturel et extrait l'intention et ses paramètres."""
    return intent_parser.parse(request.query)


@app.post("/api/v1/interact", response_model=InteractionResponse, tags=["Interaction"])
async def interact(request: InteractionRequest):
    """Point d'entrée universel pour les requêtes vocales ou textuelles.
    
    1. Parse l'intention
    2. Route vers le bon connecteur (en Phase 1: réponses de simulation / stub)
    3. Formule une réponse parlée / textuelle
    """
    parsed = intent_parser.parse(request.query)

    # Réponse temporaire / simulation avant branchement complet des connecteurs en Phase 2
    match parsed.intent:
        case IntentType.GET_MEAL_PLAN:
            period = parsed.parameters.get("period", "ce soir")
            spoken = f"D'après le planning pour {period}, vous avez prévu : Lasagnes maison et salade verte."
        case IntentType.ADD_SHOPPING_ITEM:
            item = parsed.parameters.get("item", "l'article")
            spoken = f"C'est noté, j'ai ajouté {item} à votre liste de courses."
        case IntentType.GET_SHOPPING_LIST:
            spoken = "Voici les articles sur votre liste de courses : Pain, Pommes, Lait d'avoine."
        case IntentType.GET_BUDGET_BALANCE:
            cat = parsed.parameters.get("category", "général")
            spoken = f"Il vous reste actuellement 145 euros sur votre budget {cat} pour ce mois."
        case IntentType.LOG_EXPENSE:
            amount = parsed.parameters.get("amount", 0)
            cat = parsed.parameters.get("category", "divers")
            spoken = f"C'est enregistré : {amount} euros ajoutés aux dépenses {cat}."
        case IntentType.ADD_TASK:
            task = parsed.parameters.get("task", "tâche")
            spoken = f"Tâche enregistrée dans Google Tasks : {task}."
        case IntentType.LIST_TASKS:
            spoken = "Vous avez 2 tâches aujourd'hui : Rappeler le garage et arroser les plantes."
        case IntentType.SUMMARIZE_EMAILS:
            spoken = "Vous avez 1 e-mail important de votre banque concernant un relevé mensuel."
        case IntentType.TOGGLE_DEVICE:
            device = parsed.parameters.get("device", "appareil")
            action = "allumée" if parsed.parameters.get("action") == "on" else "éteinte"
            spoken = f"La {device} a bien été {action}."
        case _:
            spoken = "Je n'ai pas bien compris votre demande. Pouvez-vous reformuler ?"

    return InteractionResponse(
        success=parsed.intent != IntentType.UNKNOWN,
        spoken_response=spoken,
        intent=parsed,
        data=parsed.parameters,
    )
