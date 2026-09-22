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
| **Étape 1** | Sécurisation de l'API & Authentification par clé API (`X-API-Key`) | 🟢 Réalisé | En attente de validation utilisateur | ✅ 133/133 tests verts (TDD) |
| **Étape 2** | Adaptateur Webhook Mobile (Interopérabilité HTTP Shortcuts & Android) | ⚪ À venir | En attente | TDD (Red $\rightarrow$ Green) |
| **Étape 3** | Micro-Web App PWA Mobile embarquée (Reconnaissance vocale STT & Synthèse TTS) | ⚪ À venir | En attente | Tests unitaires & routes |
| **Étape 4** | Tunnel sécurisé distant (Cloudflare Tunnel / ngrok) & Guide d'installation Android | ⚪ À venir | En attente | Validation réseau HTTPS |
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

### ⚪ Étape 2 : Adaptateur Webhook Mobile (HTTP Shortcuts & Android)
* **Objectif :** Permettre à des applications Android de raccourcis/widgets (ex: *HTTP Shortcuts*, *Tasker*, widgets vocaux) d'envoyer des requêtes et de recevoir une réponse formatée pour la lecture vocale native (Android Text-to-Speech).
* **Spécifications fonctionnelles & techniques :**
  * Tolérance sur le payload d'entrée (`query` ou `text`).
  * Réponse épurée optimisée pour les boîtes de dialogue et la synthèse vocale TTS mobile.
* **Démarche TDD Strict :**
  * 🔴 **Phase Rouge :** Rédaction des tests d'interopérabilité mobile.
  * 🟢 **Phase Verte :** Implémentation de la route `/api/v1/mobile/interact` ou enrichissement de `/api/v1/interact`.
  * 🔵 **Phase Refactor :** Typage Pydantic strict.

---

### ⚪ Étape 3 : Micro-Web App PWA Mobile embarquée (STT / TTS & Visualisation)
* **Objectif :** Proposer une interface web mobile moderne servie directement par FastAPI (`/app`), installable comme une application native sur l'écran d'accueil Android (PWA).
* **Spécifications fonctionnelles & techniques :**
  * Design responsive épuré (dark mode, typographie soignée, boutons larges pour le supermarché).
  * Gros bouton Micro exploitant la reconnaissance vocale native du navigateur (*Web Speech API*).
  * Synthèse vocale de la réponse (*SpeechSynthesis API*) pour écouter l'assistant au casque ou haut-parleur.
  * Cartes visuelles : affichage du menu du jour et liste de courses dynamique avec cases à cocher en direct.
  * Fichier `manifest.json` pour installation en un clic sur Android.
* **Démarche :**
  * Fichiers statiques légers (HTML/CSS/JS Vanilla) dans `app/static/`.
  * Tests d'intégration des routes statiques.

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
