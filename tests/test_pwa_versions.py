"""Seul test des versions de la PWA (constantes dans tests/pwa_versions.py)."""
from tests.js_helpers import rendered_html, static_source
from tests.pwa_versions import APP_JS, SW_CACHE


def test_service_worker_cache_version():
    assert f'const CACHE_NAME = "{SW_CACHE}";' in static_source("sw.js")


def test_app_script_version():
    assert APP_JS in rendered_html()
