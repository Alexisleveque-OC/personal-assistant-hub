"""Router FastAPI pour les raccourcis mobiles Android (HTTP Shortcuts, Tasker, widgets)."""
from typing import Optional
from fastapi import APIRouter, Depends, Query, Request, BackgroundTasks
from fastapi.responses import PlainTextResponse

from app.core.security import verify_api_key
from app.core.models import InteractionRequest, InteractionResponse
from app.routers.interact import interact

router = APIRouter(
    prefix="/api/v1/mobile",
    tags=["Mobile"],
    dependencies=[Depends(verify_api_key)],
)


@router.post(
    "/interact",
    response_model=InteractionResponse,
    operation_id="mobile_interact_post",
)
@router.get(
    "/interact",
    response_model=InteractionResponse,
    operation_id="mobile_interact_get",
)
async def mobile_interact(
    req: Request,
    background_tasks: BackgroundTasks = None,
    text: Optional[str] = Query(None, description="Texte de la requête pour appels GET ou query params"),
    payload: Optional[InteractionRequest] = None,
):
    """Adaptateur optimisé pour les raccourcis mobiles Android (HTTP Shortcuts, Tasker, widgets).

    - Accepte GET (?text=...) ou POST (JSON avec 'text', 'message' ou 'query').
    - Retourne du JSON ou du texte brut directement si 'Accept: text/plain' est spécifié.
    """
    query_text = ""
    source = "android"
    session_id = "mobile_session"
    context = {}

    if payload:
        query_text = payload.query
        source = payload.source or source
        session_id = payload.session_id or session_id
        context = payload.context or context
    elif text is not None:
        query_text = text

    # Si la requête POST contenait un JSON brut avec des clés alternatives
    if not query_text and req.method == "POST":
        try:
            body = await req.json()
            if isinstance(body, dict):
                query_text = (
                    body.get("query")
                    or body.get("text")
                    or body.get("message")
                    or body.get("prompt")
                    or ""
                )
                source = body.get("source", source)
                session_id = body.get("session_id", session_id)
        except Exception:
            pass

    interact_req = InteractionRequest(
        query=query_text,
        source=source,
        session_id=session_id,
        context=context,
    )
    res = await interact(interact_req, background_tasks=background_tasks)

    # Réponse texte brut si demandée (ex: pour être lue directement par le TTS Android)
    accept_header = req.headers.get("accept", "")
    if "text/plain" in accept_header:
        return PlainTextResponse(content=res.spoken_response)

    return res
