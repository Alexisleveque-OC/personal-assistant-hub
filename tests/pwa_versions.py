"""Versions courantes de la PWA : le SEUL endroit des tests à modifier lors d'un bump.

Bumper `SW_CACHE` à chaque changement d'un asset précaché (sw.js, CACHE_NAME) ;
`APP_JS` suit le paramètre ?v= du script principal dans index.html.
"""
SW_CACHE = "pah-pwa-cache-v58"
APP_JS = "/static/app.js?v=31.0"
