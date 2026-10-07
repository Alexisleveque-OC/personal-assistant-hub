"""Router FastAPI pour les routes PWA (interface web mobile, manifest et Service Worker)."""
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

router = APIRouter(include_in_schema=False)

STATIC_DIR = Path(__file__).parent.parent / "static"


def mount_static_files(app):
    """Monte le dossier static sur l'application FastAPI principale."""
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@router.get("/app")
async def get_app_ui():
    """Sert l'interface mobile PWA."""
    index_path = STATIC_DIR / "index.html"
    return FileResponse(
        index_path,
        media_type="text/html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@router.get("/manifest.json")
async def get_manifest():
    """Sert le manifest Web App pour l'installation Android."""
    manifest_path = STATIC_DIR / "manifest.json"
    return FileResponse(
        manifest_path,
        media_type="application/manifest+json",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@router.get("/sw.js")
async def get_service_worker():
    """Sert le Service Worker PWA."""
    sw_path = STATIC_DIR / "sw.js"
    return FileResponse(
        sw_path,
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )
