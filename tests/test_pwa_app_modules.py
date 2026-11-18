"""Refacto anti-tokens, lot 4 : app.js ne garde que l'orchestration du démarrage ;
la coquille (feuilles, menu), le mains-libres et le service worker ont leurs modules."""
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"

def _read(rel: str) -> str:
    return (STATIC / rel).read_text(encoding="utf-8")


def test_app_js_only_orchestrates_the_startup():
    assert len(_read("app.js").splitlines()) < 120


def test_service_worker_registration_still_reloads_once_on_update():
    js = _read("js/sw_register.js")
    assert 'navigator.serviceWorker.register("/sw.js")' in js
    assert '"controllerchange"' in js and "window.location.reload()" in js
