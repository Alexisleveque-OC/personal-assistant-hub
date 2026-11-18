"""Marqueurs des tests qui appellent les vrais services (jamais lancés par défaut, même si .env a les identifiants)."""
import os

import pytest

requires_live_sheets = pytest.mark.skipif(
    os.environ.get("RUN_LIVE_SHEETS") != "1",
    reason="Lecture des vrais Google Sheets : définir RUN_LIVE_SHEETS=1.",
)
