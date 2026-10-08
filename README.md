# Personal Assistant Hub 🧠⚡

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Pydantic v2](https://img.shields.io/badge/Pydantic-v2.10+-E92063.svg?logo=pydantic&logoColor=white)](https://docs.pydantic.dev/)
[![Tests Pytest](https://img.shields.io/badge/tests-389%20passed%20%7C%20100%25-brightgreen.svg?logo=pytest&logoColor=white)](https://docs.pytest.org/)
[![Architecture Modulaire](https://img.shields.io/badge/architecture-Domain--First%20%7C%20APIRouters-purple.svg)](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
[![Code Style: TDD Strict](https://img.shields.io/badge/code%20style-TDD%20Strict-success.svg)](https://en.wikipedia.org/wiki/Test-driven_development)

Un **hub d'orchestration personnel intelligent, modulaire et orienté production**, conçu pour piloter son quotidien numérique (planning des repas, courses en magasin, entraînement running & coaching sportif, budget, tâches et domotique) en langage naturel, par la voix ou par écrit.

> *« Développeur backend issu d'une reconversion de la boulangerie, j'ai gardé le goût des choses bien faites, du pétrissage rigoureux et des bases solides. Ce projet n'est pas un énième wrapper d'API généré à la va-vite : c'est un véritable laboratoire d'ingénierie logicielle appliqué à mes besoins réels, développé en TDD strict et pensé pour tourner en conditions réelles 24h/24. »*  
> — **Alexis Lévêque**

---

## 🎯 Pourquoi ce projet ? (Le constat)

Entre les tableurs Google Sheets de repas et de sport, les listes de courses partagées, les séances Strava, les rappels Google Tasks et les objets connectés, nos données du quotidien sont souvent dispersées dans des silos hermétiques.

L'objectif de **Personal Assistant Hub** est d'unifier ces outils derrière une **API centrale unique**, pilotable en langage naturel :
1. **Zéro friction :** Poser une question spontanée (*« Qu'est-ce qu'on mange ce soir ? »*, *« Qu'est-ce que j'ai comme séance aujourd'hui ? »*, *« Il me reste quoi à acheter au rayon Fruits ? »*) et obtenir une réponse instantanée.
2. **Intelligence Hybride Réactive (< 1-2s) :** Un cerveau LLM (Google Gemini Flash) avec auto-découverte et dialogues multi-tours, épaulé par un préchauffage du cache mémoire en RAM au boot et un repli déterministe local en cas de panne réseau.
3. **Mini-Coach Sportif Intégré (Otis) :** Suivi d'entraînement running et renforcement, calculs physiologiques (allure, km-effort, charge RPE), prévention des blessures (périostite) et gamification dopaminée (badges pop-culture).
4. **Robustesse d'artisan :** 389 tests automatisés à 100% au vert, validation stricte des contrats par Pydantic v2, base relationnelle SQLite locale ultra-rapide (WAL mode) avec réplication continue Cloud (Litestream), architecture modulaire en sous-routeurs et handlers spécialisés.

---

## 🏛️ Architecture & Principes de Conception

Le projet suit les principes de **Clean Architecture** et de découpage **Domain-First** (post-refactoring Phase 5 bis) :

```
personal-assistant-hub/
├── app/
│   ├── main.py                  # Point d'entrée épuré (< 85 lignes) : cycle de vie & inclusion des routeurs
│   ├── config.py                # Configuration typée (pydantic-settings, .env)
│   ├── core/                    # Cœur applicatif universel
│   │   ├── dependencies.py      # Injection de dépendances & singletons (0 import circulaire)
│   │   ├── intent_parser.py     # Moteur NLU déterministe & fallback local
│   │   ├── date_resolver.py     # Résolveur temporel intelligent (relatif, absolu, midi/soir)
│   │   ├── models.py            # Contrats de données stricts (Pydantic v2)
│   │   ├── session_manager.py   # Mémoire de dialogue multi-tours
│   │   ├── audio/               # Pipeline audio direct & normalisation phonétique
│   │   │   ├── phonetic_normalizer.py
│   │   │   └── stt_service.py
│   │   ├── vision/              # Analyse multimodale d'images & screenshots (Gemini Flash Vision)
│   │   │   └── vision_service.py
│   │   └── llm/                 # Intégration LLM (Gemini Client, Structured Outputs)
│   ├── routers/                 # Contrôleurs HTTP modulaires (APIRouter)
│   │   ├── system.py            # Santé (/health), métriques LLM, logs d'audit & auto-apprentissage
│   │   ├── second_brain.py      # Second Cerveau CRUD & ingestion visuelle (/api/v1/second-brain/*)
│   │   ├── pwa.py               # Routes statiques PWA (/app, manifest.json, sw.js)
│   │   ├── meals.py             # Planning repas & ingrédients (/api/v1/meals/*)
│   │   ├── sport.py             # Séances, synthèses hebdo, dashboard (/api/v1/sport/*)
│   │   ├── strava.py            # Ingestion & webhooks Strava (/api/v1/integrations/strava/*)
│   │   └── mobile.py            # Adaptateur vocal, audio direct & webhooks (/api/v1/interact/*)
│   ├── handlers/                # Aiguillage métier découplé des contrôleurs HTTP
│   │   ├── meals_handler.py     # Traitement des intentions Repas & Courses
│   │   ├── sport_handler.py     # Traitement des intentions Sport & Coaching Otis
│   │   ├── assistant_handler.py # Traitement conversationnel & clarifications
│   │   └── undo_handler.py      # Commande d'annulation contextuelle immédiate (Undo)
│   ├── connectors/              # Connecteurs tiers isolés et interchangeables
│   │   ├── base.py              # Interface commune des connecteurs
│   │   ├── sheets/              # Google Sheets Repas & Courses (Planning, Recettes, Rayons)
│   │   └── sport/               # Suivi running, calculs de charge & Coach Otis
│   └── static/                  # Interface utilisateur Web PWA (ES6 Modules)
│       ├── js/views/            # Vues modulaires (vocal, sport, meals, second_brain_view.js)
│       ├── css/                 # Styles graphiques & thème sombre Monstera
│       └── sw.js                # Service Worker v15 (mise en cache & offline)
├── hub_data.db                  # Base de données SQLite locale unifiée (mode WAL haute performance)
├── tests/                       # Suite de 386 tests automatisés (Unitaires, Mocks & E2E)
├── docs/                        # Guides de déploiement Cloud & documentation technique
├── AGENTS.md                    # Directives d'ingénierie agentique, TDD strict & Git
├── SPEC.md                      # Cahier des charges et backlog d'implémentation
└── requirements.txt             # Dépendances Python verrouillées
```

### Les piliers techniques :
* **TDD Strict (Test-Driven Development) :** Tout développement commence par un test unitaire rouge validant le contrat avant l'écriture du code de production (Red $\rightarrow$ Green $\rightarrow$ Refactor).
* **Pattern Connecteurs :** Chaque service externe dispose d'une abstraction et d'un mock autonome pour s'exécuter hors-ligne sans dépendance réseau lors des tests et démos.
* **Résolution contextuelle & Dialogue multi-tours :** Maintien de l'état de session, clarifications ciblées de rayon, confirmation de recettes et réajustements a posteriori.
* **Cache Mémoire & Asynchronisme :** Préchauffage des catalogues au boot du serveur (`warmup_cache`) et écritures externes en arrière-plan (`BackgroundTasks`) pour garantir un retour vocal immédiat (< 1-2s).
* **Fail-Fast Explicite :** Gestion d'erreurs déterministe avec messages contextualisés et typés en cas d'anomalie.

---

## 🚀 Modules Opérationnels

### 🥗 1. Repas & Courses (Google Sheets & PWA) — [🟢 Opérationnel]
* **Planning annuel dynamique :** Consultation midi et soir avec bascule intelligente selon l'heure de la journée.
* **Carnet de recettes (>1000 recettes) :** Recherche tolérante aux tirets/accents et ajout ciblé dans la liste d'attente avec gestion des exclusions (*« Ajoute la raclette sauf la charcuterie »*).
* **Courses en magasin & Batch Sync :** Catégorisation dynamique par rayons, cochage tactile instantané en magasin et synchronisation groupée en lot (*« 🏁 J'ai fini ! »*) préservant les cases à cocher Google Sheets. Réinitialisation explicite le samedi.

### 🏃 2. Sport Running & Mini-Coach Otis — [🟢 Opérationnel]
* **Carnet d'entraînement 360° :** Suivi des séances (EF, Fractionné, Sortie Longue, Seuil, Renforcement) avec calculs physiologiques automatiques (Km-Effort, allure min/km, vitesse, charge RPE).
* **Synthèse & Alertes de Sécurité :** Dashboard hebdomadaire de charge, règle de sécurité des +10% max et alertes ciblées pour la prévention des périostites tibiales.
* **PWA Sport Interactive :** Vue chronologique des séances, historique des semaines avec accordéons dépliables, jauges SVG et pop-up de ressenti RPE tactile.
* **Gamification Pop-Culture :** Système de badges et de trophées dopaminés (Astérix, Le Seigneur des Anneaux, Brandon Sanderson) célébrant la régularité et les records personnels.
* **Passerelle Strava :** Ingestion automatique d'activités via webhooks.

### 📱 3. Interface Mobile Vocale PWA & Conteneurisation — [🟢 Opérationnel]
* **Web App PWA installable :** Micro réactif, synthèse vocale (TTS), Service Worker v12 avec mise en cache et fonctionnement hors-ligne.
* **Docker & CI/CD Cloud :** Image de production ultra-légère (`python:3.12-slim`), pipeline GitHub Actions déployant automatiquement sur chaque merge dans `main`.

### 🧠 4. Second Cerveau, Moteur Vocal & Auto-Apprentissage — [🟢 Opérationnel]
* **Socle de persistance SQLite WAL (`hub_data.db`) :** Journal conversationnel d'audit (`conversation_logs`) avec capture de la latence, des tokens, du modèle et endpoints d'audit/feedbacks.
* **Auto-apprentissage vocal interactif (`teach_assistant`) :** Correction d'erreurs à la voix (*« Quand je dis renfort je veux dire renforcement »*), table `user_learnings` et injection dynamique des règles dans le prompt système sans toucher au code.
* **Second Cerveau compartimenté & dynamique :** Classification automatique des notes en 5 catégories (`dev_idea`, `bug_report`, `thought`, `preference`, `task`) et découverte de catégories personnalisées (voyage, cuisine, finances...).
* **Ingestion multimodale visuelle (Gemini Flash Vision) :** Capture et envoi d'images/screenshots (`POST /api/v1/second-brain/notes/image`), extraction de résumés structurés et interception native du **coller presse-papier (Ctrl+V)** dans la PWA.
* **Bouton d'annulation immédiate (« Undo ») :** Intention `undo_last_action` et composant flottant `#undo-toast` permettant d'annuler en 1 tap ou à la voix la dernière action (suppression d'une note créée par erreur, ajout de course, etc.).
* **Pipeline Audio Direct & Normalisation Phonétique :** Traitement de flux audio bruts (`/api/v1/interact/audio`), VAD tolérant aux hésitations (1.5s - 2.5s) via Web Audio API, mode Push-to-Talk et filtre phonétique préventif (`phonetic_normalizer.py`).

---

## 🗺️ Backlog & Feuilles de Route

- [x] **Phase 1 : Socle technique & Bonnes pratiques** (FastAPI, Pytest, Pydantic v2, WSL)
- [x] **Phase 2 : Connecteur Repas & Courses Google Sheets** (Planning, Recettes, Apps Script)
- [x] **Phase 3 : Interface Mobile & Entrées Vocales PWA** (PWA Android, Audio TTS/STT, Service Worker)
- [x] **Phase 3 bis : Conteneurisation & CI/CD Cloud 24h/24** (Docker, GitHub Actions, Cloud Secrets)
- [x] **Phase 4 : Moteur Conversationnel LLM Gemini & Réactivité < 1-2s** (Structured Outputs, Cache RAM)
- [x] **Phase 5 : Module Sport Running & Mini-Coach Otis** (Dashboard, RPE, Périostite, Gamification, Strava)
- [x] **Phase 5 bis : Refactoring Modulaire Architectural** (Clean Architecture, APIRouters, Handlers)
- [x] **Phase 5 ter : Retours d'Expérience UX (Sport & Courses)** (Historique Séances/Semaines, Batch Sync)
- [x] **Phase 6 : Moteur Vocal Haute-Fidélité, Mémoire Long-terme & Second Cerveau**
  - Socle SQLite unifié en mode WAL (`hub_data.db`) & journal d'audit des conversations
  - Second Cerveau compartimenté avec ingestion multimodale d'images (Gemini Vision & Ctrl+V)
  - Auto-apprentissage vocal (`teach_assistant`) avec injection dynamique dans le prompt
  - Commande d'annulation réversible immédiate (*Undo*) et toast tactile interactif
  - Pipeline STT direct (`/api/v1/interact/audio`), normalisation phonétique et VAD tolérant (1.5-2.5s)
  - Interface PWA dédiée (vue Second Cerveau, filtres pills, audit des échanges & correction)
- [ ] **Phase 7 : Otis Live Runner (Entraînement Running en Direct, Tracking GPS Local, Guidage Vocal & Périostite)**
  - Tracking GPS temps réel via Foreground Service Capacitor temporaire (préservation batterie au repos, contournement de Strava & Decathlon)
  - Guidage vocal d'intervalles & fractionné avec bips 3-2-1 dans les écouteurs et gestion Spotify Connect (audio ducking)
  - Adaptation dynamique de charge et allègement immédiat en cas d'alerte périostite
  - Checklist interactive de renforcement musculaire (clic & voix)
  - Compatibilité montres sportives (import direct de fichiers `.FIT` Garmin)
- [ ] **Phase 8 : Migration Sport (Google Sheets ➔ Base SQLite locale)**
  - Stockage local relationnel haute performance (< 1 ms de latence, fin des quotas Google Sheets)
  - Résolution sémantique de *« ma dernière séance »* et dates naturelles orales
- [ ] **Phase 9 : Connecteurs Organisationnels (Google Agenda, Google Tasks, Gmail)**
- [ ] **Phase 10 : Chronique Matinale Audio (Mini-Podcast Quotidien via Edge-TTS)**
- [ ] **Phase 11 : Connecteur Budget (Google Sheets)**
- [ ] **Phase 12 : Interfaces Vocales & Messageries (Amazon Alexa Skill, Bot Telegram)**
- [ ] **Phase 13 : Connecteurs Professionnels (Mails Pro, Jira, Trello)**
- [ ] **Phase 14 : Domotique (Tuya / Home Assistant)**

---

## 🛠️ Démarrage Rapide

### 1. Prérequis
* Python 3.12+
* Environnement Linux / WSL recommandé

### 2. Installation

```bash
# Cloner le dépôt
git clone https://github.com/Alexisleveque-OC/personal-assistant-hub.git
cd personal-assistant-hub

# Créer et activer l'environnement virtuel
python3 -m venv .venv
source .venv/bin/activate

# Installer les dépendances
pip install -r requirements.txt
```

### 3. Configuration (`.env`)

Dupliquez `.env.example` (ou créez `.env`) :
```ini
APP_ENV=development
LOG_LEVEL=INFO
API_KEY=votre_cle_api_secrete
GOOGLE_SERVICE_ACCOUNT_INFO={"type": "service_account", ...} # ou chemin vers credentials.json
GEMINI_API_KEY=votre_cle_gemini_flash
```

### 4. Lancer la suite de tests (Boucle de rétroaction TDD)

```bash
.venv/bin/pytest -v
```
> **389 tests automatisés exécutés à 100% au vert en ~22 secondes.**

### 5. Lancer le serveur de développement

```bash
.venv/bin/uvicorn app.main:app --reload --port 8000
```
* **Application Web PWA :** `http://localhost:8000/app`
* **Documentation OpenAPI (Swagger) :** `http://localhost:8000/docs`

---

## 👨‍💻 À propos de l'Auteur

**Alexis Lévêque** — *Développeur Backend Web (PHP / Symfony & Python)*
* 📍 La Rochelle, France
* 🔗 [LinkedIn](https://www.linkedin.com/in/alexis-l%C3%A9v%C3%AAque-04b38b1b2/) • [GitHub](https://github.com/Alexisleveque-OC)
* 💡 *Engagé pour le code propre, la maintenabilité, l'architecture modulaire et les tests automatisés.*
