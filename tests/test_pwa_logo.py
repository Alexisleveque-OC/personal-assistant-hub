"""PWA : nouveau logo « Sceau du scribe » (refonte UX, étape 9, demandé le 10/11).

Le kit vient de icons/ (hors git, consignes icons/ICONES.md) : icônes PWA, favicons, apple-touch-icon et
logo-otis.svg, servis sous /static/icons/. Les anciennes icônes (icon.svg, icon.png) disparaissent.
"""
import re
import struct

from fastapi.testclient import TestClient

from app.main import app
from tests.js_helpers import rendered_html

client = TestClient(app)

KIT_PNG_SIZES = {
    "icon-192.png": 192,
    "icon-512.png": 512,
    "icon-maskable-192.png": 192,
    "icon-maskable-512.png": 512,
    "apple-touch-icon.png": 180,
    "favicon-32.png": 32,
    "favicon-16.png": 16,
}
LOGO = "/static/icons/logo-otis.svg"
BRAND_DARK = "#141416"


def _head() -> str:
    html = rendered_html()
    return html[: html.index("</head>")]


def _png_size(data: bytes) -> tuple[int, int]:
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "pas un PNG"
    return struct.unpack(">II", data[16:24])


def test_kit_icons_are_served_with_their_expected_sizes():
    for name, size in KIT_PNG_SIZES.items():
        res = client.get(f"/static/icons/{name}")
        assert res.status_code == 200, name
        assert _png_size(res.content) == (size, size), name
    for svg in ("favicon.svg", "logo-otis.svg"):
        res = client.get(f"/static/icons/{svg}")
        assert res.status_code == 200, svg
        assert "svg" in res.headers.get("content-type", "")


def test_old_icons_are_removed():
    for old in ("icon.svg", "icon.png"):
        assert client.get(f"/static/icons/{old}").status_code == 404, old


def test_manifest_uses_the_new_icons_and_brand_colors_and_keeps_the_rest():
    data = client.get("/manifest.json").json()
    assert data["background_color"] == BRAND_DARK
    assert data["theme_color"] == BRAND_DARK
    icons = {(i["src"].split("?")[0], i["sizes"], i["purpose"]) for i in data["icons"]}
    assert icons == {
        ("/static/icons/icon-192.png", "192x192", "any"),
        ("/static/icons/icon-512.png", "512x512", "any"),
        ("/static/icons/icon-maskable-192.png", "192x192", "maskable"),
        ("/static/icons/icon-maskable-512.png", "512x512", "maskable"),
    }
    assert all(i["type"] == "image/png" for i in data["icons"])
    # Seules icons / background_color / theme_color changent : l'identité de l'installation reste la même.
    assert data["id"] == "/app?v=4"
    assert data["name"] == "Assistant Personnel Hub"
    assert data["short_name"] == "Otis"  # libellé sous l'icône (demande du 18/11)
    assert [s["url"] for s in data["shortcuts"]] == ["/app?action=meal_today", "/app?action=shopping_list"]


def test_head_declares_favicons_apple_touch_icon_and_theme_color():
    head = _head()
    assert re.search(r'<link rel="icon" href="/static/icons/favicon\.svg[^"]*" type="image/svg\+xml"', head)
    assert re.search(r'<link rel="icon" href="/static/icons/favicon-32\.png[^"]*" sizes="32x32" type="image/png"', head)
    assert re.search(r'<link rel="icon" href="/static/icons/favicon-16\.png[^"]*" sizes="16x16" type="image/png"', head)
    assert re.search(r'<link rel="apple-touch-icon" href="/static/icons/apple-touch-icon\.png[^"]*"', head)
    assert head.count('rel="apple-touch-icon"') == 1
    assert f'<meta name="theme-color" content="{BRAND_DARK}"' in head
    assert "/icons/icon.svg" not in head


def test_otis_avatars_show_the_logo_instead_of_a_letter():
    html = rendered_html()
    avatars = re.findall(r'<img class="avatar-otis[^"]*"[^>]*>', html)
    assert len(avatars) == 3  # « Dernières actions », modèle de message d'Otis, en-tête du menu
    assert all(f'src="{LOGO}"' in a and 'alt=""' in a for a in avatars)
    assert not re.search(r'class="avatar-otis[^"]*"[^>]*>O<', html)
    chat_view = client.get("/static/js/views/chat_view.js").text
    assert 'document.createElement("img")' in chat_view and f'"{LOGO}"' in chat_view
    assert 'avatar.textContent = "O"' not in chat_view


def test_service_worker_precaches_the_new_logo_kit():
    sw = client.get("/sw.js").text
    for name in [*KIT_PNG_SIZES, "favicon.svg", "logo-otis.svg"]:
        assert f'"/static/icons/{name}"' in sw, name
    assert "/icons/icon.svg" not in sw


def test_home_screen_label_is_otis_on_ios_too():
    assert '<meta name="apple-mobile-web-app-title" content="Otis" />' in _head()
