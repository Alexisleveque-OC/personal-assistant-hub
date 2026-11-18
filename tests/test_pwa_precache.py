"""Précache du service worker : chaque module JS est mis en cache, chaque entrée existe."""
import re

from tests.js_helpers import STATIC, static_source


def _precached() -> list[str]:
    assets = re.search(r"ASSETS_TO_CACHE = \[(.*?)\];", static_source("sw.js"), re.S).group(1)
    return re.findall(r'"([^"]+)"', assets)


def test_every_js_module_is_precached():
    precached = set(_precached())
    modules = sorted(f"/static/{p.relative_to(STATIC).as_posix()}" for p in (STATIC / "js").rglob("*.js"))
    assert modules and [m for m in modules if m not in precached] == []


def test_every_precached_static_file_exists():
    static = [path for path in _precached() if path.startswith("/static/")]
    missing = [path for path in static if not (STATIC / path.removeprefix("/static/")).is_file()]
    assert missing == []
