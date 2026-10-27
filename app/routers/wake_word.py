"""Router FastAPI du modèle Vosk (détection locale du mot-clé « Otis »).

Le modèle (~42 Mo) dépasse la limite de 32 Mio imposée par Cloud Run aux réponses HTTP/1 de taille connue
(erreur 500) : il est donc envoyé en flux (Transfer-Encoding: chunked), sans Content-Length.
"""
from pathlib import Path
from typing import Iterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

router = APIRouter(include_in_schema=False)

MODEL_PATH = Path(__file__).parent.parent / "static" / "vendor" / "vosk" / "model.tar.gz"
CHUNK_SIZE = 1024 * 1024


def _read_chunks(path: Path) -> Iterator[bytes]:
    with path.open("rb") as model_file:
        while chunk := model_file.read(CHUNK_SIZE):
            yield chunk


@router.get("/vosk/model.tar.gz")
def get_vosk_model() -> StreamingResponse:
    """Sert le modèle Vosk en flux ; l'URL est versionnée côté client, d'où un cache immuable."""
    if not MODEL_PATH.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Modèle Vosk absent ({MODEL_PATH}). Lancez : python scripts/fetch_vosk_assets.py",
        )
    return StreamingResponse(
        _read_chunks(MODEL_PATH),
        media_type="application/gzip",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
