"""Récupération des assets Vosk (détection locale du mot-clé « Otis ») au build Docker ou en local.

Télécharge le runtime WASM `@lichess-org/vosk-browser` et le modèle français léger, vérifie leurs
empreintes SHA-256 figées, puis les dépose dans `app/static/vendor/vosk/` (ignoré par git).

Usage en ligne de commande :
    python scripts/fetch_vosk_assets.py [--output app/static/vendor/vosk]
"""
import argparse
import hashlib
import io
import logging
import tarfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

NPM_URL = "https://registry.npmjs.org/@lichess-org/vosk-browser/-/vosk-browser-0.0.3.tgz"
MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-fr-0.22.zip"
EXPECTED_SHA256 = {
    "npm": "4ffa35538ce5f0ab1d9ddad12553405f475e97c1fe734f8b4a5cfad2fec58fa4",
    "model": "cabf6180e177eb9b3a9a9d43a437bd5e549f3a7d09525e5d69a3fed787be12ad",
}
ASSETS_VERSION = "vosk-browser-0.0.3+vosk-model-small-fr-0.22"
NPM_DIST_FILES = ("vosk.wasm.js", "vosk.worker.js", "vosk.wasm")
MODEL_ARCHIVE = "model.tar.gz"
DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "app" / "static" / "vendor" / "vosk"


class VoskAssetError(RuntimeError):
    """Asset Vosk introuvable, corrompu ou incomplet."""


def download(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=120) as response:
        return response.read()


def verify_sha256(data: bytes, expected: str, label: str) -> None:
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise VoskAssetError(
            f"Empreinte SHA-256 invalide pour {label} : attendue {expected}, obtenue {actual}. "
            "Téléchargement corrompu ou fichier modifié à la source."
        )


def extract_npm_dist(tarball: bytes, destination: Path) -> None:
    """Extrait du paquet npm les seuls fichiers nécessaires au navigateur."""
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(tarball), mode="r:gz") as tar:
        available = {Path(member.name).name: member for member in tar.getmembers() if member.isfile()}
        missing = [name for name in NPM_DIST_FILES if name not in available]
        if missing:
            raise VoskAssetError(
                f"Fichiers absents du paquet npm : {missing}. Disponibles : {sorted(available)}"
            )
        for name in NPM_DIST_FILES:
            (destination / name).write_bytes(tar.extractfile(available[name]).read())


def repack_model(model_zip: bytes, destination: Path) -> None:
    """Réemballe le zip officiel en tar.gz avec un dossier racine `model/` (format attendu par vosk-browser)."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(model_zip)) as archive, tarfile.open(destination, "w:gz") as tar:
        for entry in archive.infolist():
            if entry.is_dir():
                continue
            parts = Path(entry.filename).parts
            if len(parts) < 2:
                raise VoskAssetError(f"Entrée inattendue hors du dossier du modèle : {entry.filename}")
            data = archive.read(entry)
            info = tarfile.TarInfo(str(Path("model", *parts[1:])))
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))


def _is_current(output: Path) -> bool:
    version_file = output / "VERSION"
    required = [output / name for name in (*NPM_DIST_FILES, MODEL_ARCHIVE)]
    return (
        version_file.exists()
        and version_file.read_text().strip() == ASSETS_VERSION
        and all(path.exists() for path in required)
    )


def fetch_vosk_assets(
    output: Path = DEFAULT_OUTPUT,
    downloader: Callable[[str], bytes] = download,
    expected: Optional[dict[str, str]] = None,
) -> None:
    expected = expected or EXPECTED_SHA256
    if _is_current(output):
        logger.info("Assets Vosk déjà présents (%s) dans %s", ASSETS_VERSION, output)
        return

    logger.info("Téléchargement du runtime Vosk : %s", NPM_URL)
    tarball = downloader(NPM_URL)
    verify_sha256(tarball, expected["npm"], "paquet npm @lichess-org/vosk-browser")

    logger.info("Téléchargement du modèle français : %s", MODEL_URL)
    model_zip = downloader(MODEL_URL)
    verify_sha256(model_zip, expected["model"], "modèle vosk-model-small-fr-0.22")

    extract_npm_dist(tarball, output)
    repack_model(model_zip, output / MODEL_ARCHIVE)
    (output / "VERSION").write_text(ASSETS_VERSION)
    logger.info("Assets Vosk prêts dans %s", output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Télécharge les assets Vosk (runtime WASM + modèle français).")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Dossier de destination")
    args = parser.parse_args()
    fetch_vosk_assets(args.output)


if __name__ == "__main__":
    main()
