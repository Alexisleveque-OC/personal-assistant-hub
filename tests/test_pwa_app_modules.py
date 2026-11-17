"""Refacto anti-tokens, lot 4 : app.js ne garde que l'orchestration du démarrage ;
la coquille (feuilles, menu), le mains-libres et le service worker ont leurs modules."""
import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"

MODULES = {
    "app_shell.js": "initShell",
    "hands_free.js": "initHandsFreeSwitch",
    "sw_register.js": "registerServiceWorker",
}


def _read(rel: str) -> str:
    return (STATIC / rel).read_text(encoding="utf-8")


def test_app_js_only_orchestrates_the_startup():
    app_js = _read("app.js")
    assert len(app_js.splitlines()) < 120
    for module, export in MODULES.items():
        assert f'from "./js/{module}"' in app_js, module
        assert f"{export}(" in app_js, export
    for moved in ("navigator.serviceWorker", "createSheetManager", "wake-word-switch", "function loadSection"):
        assert moved not in app_js, moved


def test_extracted_modules_export_their_entry_point_and_are_precached():
    sw = _read("sw.js")
    for module, export in MODULES.items():
        assert re.search(rf"export function {export}\(", _read(f"js/{module}")), module
        assert f'"/static/js/{module}"' in sw, module


def test_service_worker_registration_still_reloads_once_on_update():
    js = _read("js/sw_register.js")
    assert 'navigator.serviceWorker.register("/sw.js")' in js
    assert '"controllerchange"' in js and "window.location.reload()" in js
