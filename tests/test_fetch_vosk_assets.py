"""Récupération des assets Vosk au build (Étape 2) : paquet WASM + modèle français, empreintes figées, réemballage."""
import hashlib
import io
import tarfile
import zipfile
from pathlib import Path

import pytest

from scripts.fetch_vosk_assets import (
    ASSETS_VERSION,
    NPM_DIST_FILES,
    VoskAssetError,
    extract_npm_dist,
    fetch_vosk_assets,
    repack_model,
    verify_sha256,
)

ROOT = Path(__file__).resolve().parent.parent


def _npm_tarball(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(f"package/dist/{name}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def _model_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("vosk-model-small-fr-0.22/am/final.mdl", b"am")
        archive.writestr("vosk-model-small-fr-0.22/graph/Gr.fst", b"gr")
        archive.writestr("vosk-model-small-fr-0.22/conf/model.conf", b"conf")
    return buffer.getvalue()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_verify_sha256_rejects_tampered_download_with_context():
    with pytest.raises(VoskAssetError) as exc:
        verify_sha256(b"tampered", "0" * 64, "modèle français")
    message = str(exc.value)
    assert "modèle français" in message
    assert "0" * 64 in message
    assert _sha(b"tampered") in message


def test_verify_sha256_accepts_expected_digest():
    verify_sha256(b"ok", _sha(b"ok"), "paquet npm")


def test_extract_npm_dist_writes_only_the_browser_runtime_files(tmp_path):
    files = {name: name.encode() for name in NPM_DIST_FILES}
    files["vosk.interfaces.d.ts"] = b"types"
    destination = tmp_path / "vosk"
    extract_npm_dist(_npm_tarball(files), destination)

    assert sorted(p.name for p in destination.iterdir()) == sorted(NPM_DIST_FILES)
    assert (destination / "vosk.wasm").read_bytes() == b"vosk.wasm"


def test_extract_npm_dist_fails_fast_listing_available_files(tmp_path):
    with pytest.raises(VoskAssetError) as exc:
        extract_npm_dist(_npm_tarball({"vosk.wasm.js": b"js"}), tmp_path)
    message = str(exc.value)
    assert "vosk.wasm" in message
    assert "vosk.wasm.js" in message


def test_repack_model_uses_a_model_root_folder(tmp_path):
    destination = tmp_path / "model.tar.gz"
    repack_model(_model_zip(), destination)

    with tarfile.open(destination, "r:gz") as tar:
        names = tar.getnames()
        assert tar.extractfile("model/am/final.mdl").read() == b"am"
    assert "model/graph/Gr.fst" in names
    assert "model/conf/model.conf" in names
    assert not any("vosk-model-small-fr" in name for name in names)


def test_fetch_vosk_assets_downloads_verifies_and_writes_everything(tmp_path):
    npm = _npm_tarball({name: name.encode() for name in NPM_DIST_FILES})
    model = _model_zip()
    payloads = {"npm": npm, "model": model}
    calls = []

    def downloader(url: str) -> bytes:
        calls.append(url)
        return payloads["npm" if url.endswith(".tgz") else "model"]

    fetch_vosk_assets(tmp_path, downloader=downloader, expected={"npm": _sha(npm), "model": _sha(model)})

    assert len(calls) == 2
    for name in NPM_DIST_FILES:
        assert (tmp_path / name).exists()
    assert (tmp_path / "model.tar.gz").exists()
    assert (tmp_path / "VERSION").read_text().strip() == ASSETS_VERSION


def test_fetch_vosk_assets_skips_download_when_current_version_is_present(tmp_path):
    for name in [*NPM_DIST_FILES, "model.tar.gz"]:
        (tmp_path / name).write_bytes(b"x")
    (tmp_path / "VERSION").write_text(ASSETS_VERSION)

    def downloader(url: str) -> bytes:
        raise AssertionError(f"téléchargement inattendu : {url}")

    fetch_vosk_assets(tmp_path, downloader=downloader)


def test_vendor_folder_is_ignored_by_git():
    assert "/app/static/vendor/vosk/" in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()


def test_dockerfile_fetches_assets_after_copying_app_and_before_switching_user():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    fetch_index = dockerfile.index("python scripts/fetch_vosk_assets.py")
    assert dockerfile.index("COPY scripts/ ./scripts/") < fetch_index
    assert fetch_index < dockerfile.index("chown -R appuser:appuser /app")


def test_docker_context_excludes_local_assets_so_the_image_always_downloads_pinned_ones():
    assert "app/static/vendor/vosk" in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
