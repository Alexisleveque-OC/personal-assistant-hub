# Roadmap Feature : Interface Mobile & Entrées Vocales Android (`feat/android-voice-interface`)

> **Règle d'or (AGENTS.md) :**
> - Chaque étape doit être validée **manuellement et explicitement par l'utilisateur** avant de passer à la suivante.
> - La suite de tests automatisés (`pytest`) doit être à **100% au vert** à chaque étape.
> - Tout nouveau code de production est développé en **TDD Strict** (Phase Rouge $\rightarrow$ Phase Verte $\rightarrow$ Refactor).
> - À la fin de la feature, un **test d'intégration End-to-End (E2E)** valide le flux complet en conditions réelles sur smartphone.

---

## Vue d'ensemble des Étapes

| Étape | Description | Statut | Validation Utilisateur | Tests Automatisés |
| :--- | :--- | :---: | :---: | :---: |
| **Étape 1** | Sécurisation de l'API & Authentification par clé API (`X-API-Key`) | 🟢 Réalisé | ✅ Validé par l'utilisateur | ✅ 133/133 tests verts (TDD) |
| **Étape 2** | Adaptateur Webhook Mobile (Interopérabilité HTTP Shortcuts & Android) | 🟢 Réalisé | ✅ Validé par l'utilisateur | ✅ 141/141 tests verts (TDD) |
| **Étape 3** | Micro-Web App PWA Mobile embarquée (Reconnaissance vocale STT & Synthèse TTS) | 🟢 Réalisé | En attente de validation utilisateur | ✅ 153/153 tests verts (TDD) |
| **Étape 4** | Tunnel sécurisé distant (Cloudflare Tunnel / ngrok) & Guide d'installation Android | ⚪ À venir | En attente | Configuration HTTPS & Routines |
| **Étape 5** | Test d'intégration End-to-End (E2E) en conditions réelles sur smartphone | ⚪ À venir | En attente | Test réel sur mobile |

---

## Détail des Étapes

### 🟢 Étape 1 : Sécurisation de l'API & Authentification par clé API (`X-API-Key`)
* **Objectif :** Protéger l'API contre tout accès non autorisé lorsqu'elle sera exposée sur Internet via un tunnel HTTPS pour le smartphone.
* **Livrables & Réalisations :**
  * Variable d'environnement `API_KEY` ajoutée dans `app/config.py`.
  * Dépendance de sécurité `verify_api_key` implémentée dans `app/core/security.py` avec `APIKeyHeader(name="X-API-Key")`.
  * Mode permissif préservé si aucune clé n'est configurée (rétrocompatibilité totale).
  * Rejet strict `401 Unauthorized` si une clé est configurée et que le header est manquant ou invalide.
  * Protection appliquée sur les routes `/api/v1/*` de `app/main.py`.
  * Suite de tests TDD dans `tests/test_auth.py` : 5 nouveaux tests au vert.
  * **Suite complète : 133/133 tests au vert (100% de réussite).**

---

### 🟢 Étape 2 : Adaptateur Webhook Mobile (HTTP Shortcuts & Android)
* **Objectif :** Permettre à des applications Android de raccourcis/widgets (ex: *HTTP Shortcuts*, *Tasker*, widgets vocaux) d'envoyer des requêtes et de recevoir une réponse formatée pour la lecture vocale native (Android Text-to-Speech).
* **Livrables & Réalisations :**
  * Tolérance automatique sur le payload d'entrée (`query`, `text`, `message`, `prompt`, `q`) via `InteractionRequest.resolve_aliases` dans `app/core/models.py`.
  * Champs calculés `@computed_field` `speech` et `text` ajoutés sur `InteractionResponse` pour compatibilité directe avec les moteurs TTS Android.
  * Endpoint polyvalent `/api/v1/mobile/interact` implémenté en GET (query param `?text=...`) et POST.
  * Support du format de sortie en texte brut `text/plain` (via header `Accept: text/plain`) pour lecture vocale directe sans parsing JSON côté smartphone.
  * Traitement bienveillant des entrées vides sans crash HTTP 422.
  * Sécurité `X-API-Key` héritée et active sur les routes mobiles.
  * Suite de tests TDD dans `tests/test_mobile_webhook.py` : 8 nouveaux tests au vert.
  * **Suite complète : 141/141 tests au vert (100% de réussite).**

---

### 🟢 Étape 3 : Micro-Web App PWA Mobile embarquée (STT / TTS & Visualisation)
* **Objectif :** Proposer une interface web mobile moderne servie directement par FastAPI (`/app`), installable comme une application native sur l'écran d'accueil Android (PWA).
* **Livrables & Réalisations :**
  * **Design mobile premium (Dark mode) :** Palette violet/nuit profonde (`#0a0f1d`), typographie *Plus Jakarta Sans*, cartes glassmorphiques avec bordures subtiles et accents lumineux cyan/indigo.
  * **Reconnaissance vocale native (STT) :** Exploitation de la *Web Speech API* (`SpeechRecognition`) avec retour visuel d'écoute en temps réel (égaliseur animé et transcription en direct).
  * **Synthèse vocale intégrée (TTS) :** Lecture audio automatique des réponses via `SpeechSynthesis` en français avec bouton mute/démute rapide.
  * **Navigation mobile à trois onglets :**
    1. 🎙️ **Vocal :** Stream de messages avec bulles utilisateur/assistant, chips d'actions rapides et bouton microphone central flottant à pulsation lumineuse.
    2. 🛒 **Courses :** Liste dynamique groupée par rayons, cases à cocher interactives en 1-tap et purge des achetés.
    3. 🍽️ **Repas :** Cartes visuelles épurées des menus du midi et du soir.
  * **PWA Installable :** Fichier `manifest.json`, icône vectorielle SVG dédiée, et `sw.js` (Service Worker) pour la mise en cache applicative.
  * **Gestion clé API intégrée :** Modal de paramétrage de clé `X-API-Key` sauvegardée dans le `localStorage` du smartphone.
  * **Validation TDD :** 6 nouveaux tests dans `tests/test_pwa_routes.py`.
  * **Suite complète : 153/153 tests au vert (100% de réussite).**

---

### ⚪ Étape 4 : Tunnel sécurisé distant & Guide d'installation smartphone
* **Objectif :** Permettre au smartphone de joindre l'API en 4G/5G partout sans ouvrir de port sur la box internet.
* **Spécifications fonctionnelles & techniques :**
  * Script d'automatisation ou procédure avec Cloudflare Tunnel (`cloudflared`) / ngrok.
  * Guide pas-à-pas illustré pour l'utilisateur :
    1. Lancement du tunnel HTTPS.
    2. Ajout de la PWA à l'écran d'accueil Android.
    3. (Optionnel) Configuration du widget HTTP Shortcuts sur l'écran de verrouillage.

---

### ⚪ Étape 5 : Test d'intégration End-to-End (E2E) en conditions réelles
* **Objectif :** Validation finale avec l'utilisateur sur son smartphone Android en direct.
* **Scénarios validés :**
  * Dictée vocale : *« Qu'est-ce qu'on mange ce soir ? »*
  * Ajout d'article : *« Ajoute des bananes à la liste de courses »*
  * Consultation et coche directe d'un article au rayon Fruits sur le smartphone.
