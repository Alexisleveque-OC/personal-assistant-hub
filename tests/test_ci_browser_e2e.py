"""Étape 8 : le test E2E de navigation tourne dans la CI avec un vrai Chromium, sans alourdir l'image de prod."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_playwright_is_a_dev_dependency_only():
    dev = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
    assert "-r requirements.txt" in dev and "playwright==" in dev
    assert "playwright" not in (ROOT / "requirements.txt").read_text(encoding="utf-8")


def test_ci_workflows_install_chromium_and_require_the_browser_test():
    for workflow in ("test.yml", "deploy.yml"):
        source = (ROOT / ".github" / "workflows" / workflow).read_text(encoding="utf-8")
        assert "pip install -r requirements-dev.txt" in source, workflow
        assert "playwright install --with-deps chromium" in source, workflow
        assert 'E2E_BROWSER_REQUIRED: "1"' in source, workflow
