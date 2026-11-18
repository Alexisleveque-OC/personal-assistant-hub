"""Outils communs aux tests du front (PWA) : Node, HTML rendu, découpes de sources."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"
WINDOWS_NODE = Path("/mnt/c/Program Files/nodejs/node.exe")
NODE = shutil.which("node") or (str(WINDOWS_NODE) if WINDOWS_NODE.exists() else None)


def static_source(path: str) -> str:
    """Texte d'un fichier de app/static (ex. "sw.js", "js/api.js")."""
    return (STATIC / path).read_text(encoding="utf-8")


def js_source(*modules: str, strip_imports: bool = False) -> str:
    """Concatène des modules de app/static/js ; `strip_imports` retire leurs lignes `import`."""
    source = "\n".join(static_source(f"js/{name}") for name in modules)
    if strip_imports:
        source = "\n".join(line for line in source.splitlines() if not line.startswith("import "))
    return source


def run_node(source: str, *, parse_json: bool = True):
    """Exécute `source` comme module ES sous Node ; renvoie stdout (décodé en JSON par défaut)."""
    if not NODE:
        pytest.skip("Node.js indisponible pour exécuter le module JS")
    result = subprocess.run([NODE, "--input-type=module"], input=source, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout) if parse_json else result.stdout


def rendered_html() -> str:
    """HTML de /app sans les commentaires."""
    from fastapi.testclient import TestClient
    from app.main import app

    return re.sub(r"<!--.*?-->", "", TestClient(app).get("/app").text, flags=re.DOTALL)


def section(html: str, sheet_id: str) -> str:
    """Balisage de la <section> dont l'id est `sheet_id`."""
    start = html.index(f'id="{sheet_id}"')
    return html[start:html.index("</section>", start)]


def function_body(source: str, signature: str) -> str:
    """Corps entre accolades (inclusives) de la fonction qui commence à `signature`."""
    start = source.index(signature)
    depth, i = 0, source.index("{", start)
    for j in range(i, len(source)):
        depth += {"{": 1, "}": -1}.get(source[j], 0)
        if depth == 0:
            return source[i:j + 1]
    raise AssertionError(signature)
