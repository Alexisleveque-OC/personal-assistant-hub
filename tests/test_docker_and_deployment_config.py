"""Tests unitaires et structurels pour la conteneurisation Docker et le déploiement Cloud."""

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


def test_dockerfile_configuration():
    """Valide les bonnes pratiques de conteneurisation pour le Cloud."""
    dockerfile_path = ROOT_DIR / "Dockerfile"
    assert dockerfile_path.exists(), "Le fichier Dockerfile doit exister à la racine du projet."

    content = dockerfile_path.read_text(encoding="utf-8")

    # Image de base Python 3.12 slim
    assert "python:3.12" in content
    assert "slim" in content

    # Bonnes pratiques environnement
    assert "PYTHONUNBUFFERED=1" in content

    # Prise en charge dynamique de la variable $PORT pour Cloud Run / PaaS
    assert "PORT" in content
    assert "uvicorn app.main:app" in content
    assert "0.0.0.0" in content


def test_dockerignore_security_exclusions():
    """Valide que les fichiers sensibles et temporaires sont exclus de l'image Docker."""
    dockerignore_path = ROOT_DIR / ".dockerignore"
    assert dockerignore_path.exists(), "Le fichier .dockerignore doit exister."

    content = dockerignore_path.read_text(encoding="utf-8")
    lines = [line.strip() for line in content.splitlines() if line.strip() and not line.startswith("#")]

    # Fichiers sensibles
    assert ".env" in lines
    assert "credentials.json" in lines

    # Fichiers environnement & caches
    assert ".venv" in lines
    assert "__pycache__" in lines or "**/__pycache__" in lines
    assert ".git" in lines


def test_deploy_workflow_configuration():
    """Valide la structure du pipeline de déploiement continu GitHub Actions."""
    workflow_path = ROOT_DIR / ".github" / "workflows" / "deploy.yml"
    assert workflow_path.exists(), "Le fichier .github/workflows/deploy.yml doit exister."

    content = workflow_path.read_text(encoding="utf-8")

    # Déclenchement sur push vers main (MR fusionnée)
    assert "branches: [ main ]" in content or "branches:\n      - main" in content or "branches: [main]" in content
    assert "pytest" in content
    assert "deploy" in content
