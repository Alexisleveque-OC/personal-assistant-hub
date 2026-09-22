# Personal Assistant Hub 🧠⚡

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Pydantic v2](https://img.shields.io/badge/Pydantic-v2.10+-E92063.svg?logo=pydantic&logoColor=white)](https://docs.pydantic.dev/)
[![Tests Pytest](https://img.shields.io/badge/tests-128%20passed%20%7C%20100%25-brightgreen.svg?logo=pytest&logoColor=white)](https://docs.pytest.org/)
[![Code Style: TDD Strict](https://img.shields.io/badge/code%20style-TDD%20Strict-success.svg)](https://en.wikipedia.org/wiki/Test-driven_development)

Un **hub d'orchestration personnel intelligent, modulaire et orienté production**, conçu pour piloter son quotidien numérique (planning des repas, courses, budget, tâches et domotique) en langage naturel, par la voix ou par écrit.

> *« Développeur backend issu d'une reconversion de la boulangerie, j'ai gardé le goût des choses bien faites, du pétrissage rigoureux et des bases solides. Ce projet n'est pas un énième wrapper d'API généré à la va-vite : c'est un véritable laboratoire d'ingénierie logicielle appliqué à mes besoins réels, développé en TDD strict et pensé pour tourner en conditions réelles. »*
> — **Alexis Leveque**

---

## 🎯 Pourquoi ce projet ? (Le constat)

Entre les tableurs Google Sheets de budget, les listes de courses partagées, les rappels Google Tasks et les objets connectés, nos données du quotidien sont souvent éparpillées dans des silos hermétiques.

L'objectif de **Personal Assistant Hub** est d'unifier ces outils derrière une **API centrale unique**, pilotable en langage naturel :
1. **Zéro friction :** Poser une question spontanée (*« Qu'est-ce qu'on mange jeudi soir ? »* ou *« Il me reste quoi à acheter au rayon Fruits ? »*) et obtenir une réponse instantanée.
2. **Pragmatisme technique (No-Bullshit AI) :** Pourquoi injecter un LLM coûteux, lent et sujet aux hallucinations là où un moteur NLU déterministe avec mémoire de session et résolveur temporel répond en moins de 10 millisecondes avec une fiabilité à 100% ?
3. **Robustesse d'artisan :** 128 tests automatisés, validation stricte des contrats par Pydantic v2, détection de dérive de schéma (*Schema Drift*) et découplage total via le *Pattern Connecteurs*.

---

## 🏛️ Architecture & Principes de Conception

Le projet applique une séparation stricte des responsabilités :

```
personal-assistant-hub/
├── app/
│   ├── main.py                  # Point d'entrée FastAPI & routes REST (/api/v1/interact)
│   ├── config.py                # Configuration par variables d'environnement (.env)
│   ├── core/                    # Cœur applicatif (indépendant de toute techno externe)
│   │   ├── intent_parser.py     # Moteur NLU déterministe, extraction d'entités & exclusions
│   │   ├── date_resolver.py     # Résolveur temporel intelligent (relatif, absolu, midi/soir)
│   │   └── models.py            # Contrats de données stricts (Pydantic v2)
│   └── connectors/              # Connecteurs tiers isolés et interchangeables
│       ├── base.py              # Interface abstraite commune des connecteurs
│       └── sheets/              # Connecteur Google Sheets (Planning, Recettes, Courses)
│           ├── meals_connector.py   # Logique métier & synchronisation
│           ├── models.py            # Modélisation typée des onglets & articles
│           └── schema_validator.py  # Détection préventive de dérive de structure (Schema Drift)
├── tests/                       # Suite de tests unitaires, fonctionnels et E2E
│   ├── test_intent_parser.py    # Tests du moteur de compréhension NLU
│   ├── test_date_resolver.py    # Tests de résolution temporelle
│   ├── test_meals_connector.py  # Tests unitaires du connecteur avec mocks
│   ├── test_sheet_schema.py     # Tests de structure & conformité du tableur
│   └── test_e2e_meals_shopping.py # Tests d'intégration End-to-End réels
├── scripts/
│   └── chat.py                  # Console interactive locale avec mémoire de session
├── meal-planner/                # Intégration Google Apps Script (Sidebar & nettoyage ciblé)
├── AGENTS.md                    # Mémoire permanente & directives de développement (TDD, Git)
├── SPEC.md                      # Cahier des charges et backlog d'implémentation
└── requirements.txt             # Dépendances Python verrouillées
```

### Les piliers techniques :
* **TDD Strict (Test-Driven Development) :** Chaque méthode, chaque nuance grammaticale ou cas limite a d'abord fait l'objet d'un test unitaire rouge avant d'être implémentée (Phase Rouge $\rightarrow$ Phase Verte $\rightarrow$ Refactor).
* **Pattern Connecteurs :** Chaque service externe (Google Sheets aujourd'hui, Google Tasks, Gmail et Domotique demain) implémente une interface dédiée et dispose d'un mock pour s'exécuter hors-ligne sans dépendance réseau.
* **Résolution contextuelle des anaphores :** L'assistant maintient l'état conversationnel de la session (`session_id`) : si vous consultez une recette (*« Donnes-moi la recette du Chili »*) puis enchaînez par *« Ajoute ces ingrédients sauf le maïs »*, il résout le plat précédent, filtre les ingrédients exclus et les injecte au bon rayon.
* **Fail-Fast & Tolérance aux pannes :** En cas d'incohérence dans le Google Sheet (ex: onglet de l'année non encore créé), l'application ne s'effondre pas silencieusement mais lève une exception claire et contextualisée (`PlanningWorksheetNotFoundError`).

---

## 🚀 Fonctionnalités Implémentées

### 🥗 Connecteur Repas & Courses (Google Sheets) — *Phase 2 [Opérationnel]*
* **Consultation intelligente du planning :**
  * *« Qu'est-ce qu'on mange ce soir ? »* / *« On mange quoi ? »* (prise en compte de l'heure courante : si le midi est vide ou passé, bascule automatique sur le dîner).
  * *« Qu'est-ce qu'on mange jeudi prochain ? »* (restitution complète midi et soir).
* **Exploration du carnet de recettes & Ajout dynamique :**
  * Consultation parmi plus de 1 000 recettes répertoriées (plats classiques et recettes festives/apéro).
  * Ajout direct dans la liste d'attente : *« Ajoute les ingrédients pour faire une raclette sauf la charcuterie »*.
  * Dialogue de confirmation si un plat n'est pas répertorié (*« Je n'ai pas trouvé cette recette, voulez-vous quand même la programmer ? »*).
* **Gestion des courses en magasin :**
  * Détection automatique du rayon selon un lexique croisé (`Fruits`, `Légumes`, `Charcuterie`, `Entretien`, etc.).
  * *« J'ai quoi à acheter au rayon Fruits ? »* (interroge `Cette semaine` en distinguant les articles déjà cochés des articles restants).
  * *« Il me reste quoi à acheter ? »* (synthèse globale des articles non cochés).
  * *« J'ai tout acheté »* ou *« J'ai acheté le lait et les pommes »* (coche comme acheté et nettoyage ciblé).
* **Intégration Apps Script :**
  * Synchronisation bidirectionnelle avec la barre latérale du Google Sheet (`meal-planner`). Les articles en attente sont pré-cochés automatiquement lors de la génération de la feuille d'impression hebdomadaire.

---

## 🗺️ Roadmap du Projet

- [x] **Phase 1 : Socle technique & Bonnes pratiques** (FastAPI, Pytest, Pydantic, Git)
- [x] **Phase 2 : Connecteur Repas & Courses Google Sheets** (128 tests au vert, TDD strict, Apps Script)
- [ ] **Phase 3 : Interface Mobile & Entrées Vocales (Android)** *(En cours)*
  - Exposition sécurisée (Tunnel HTTPS / API Key)
  - Micro-Web App PWA optimisée mobile (Web Speech STT / TTS)
  - Widgets et raccourcis vocaux Android (HTTP Shortcuts)
- [ ] **Phase 4 : Tâches & Mails (Google Tasks & Gmail)**
  - Synthèse vocale des tâches de la journée & création de rappels
  - Détection et résumé des e-mails prioritaires (anti-bruit/newsletters)
- [ ] **Phase 5 : Connecteur Budget (Google Sheets)**
  - Enregistrement des dépenses au fil de l'eau
  - Suivi des plafonds par catégorie & alertes de dépassement
- [ ] **Phase 6 : Domotique & Intégration Enceintes (Alexa)**
  - Contrôle d'équipements connectés (prises connectées, scènes)

---

## 🛠️ Démarrage Rapide

### 1. Prérequis
* Python 3.12+
* Un compte Google Cloud avec API Google Sheets activée (compte de service)

### 2. Installation

```powershell
# Cloner le dépôt
git clone https://github.com/Alexisleveque-OC/personal-assistant-hub.git
cd personal-assistant-hub

# Créer et activer l'environnement virtuel
python -m venv .venv
.\.venv\Scripts\Activate.ps1    # Sur Windows
# source .venv/bin/activate     # Sur Linux/macOS

# Installer les dépendances
pip install -r requirements.txt
```

### 3. Configuration (`.env`)

Créez un fichier `.env` à la racine (ou dupliquez `.env.example`) :
```ini
APP_ENV=development
LOG_LEVEL=INFO
SERVICE_ACCOUNT_FILE=credentials/service_account.json
MEALS_SPREADSHEET_NAME=Semaine de repas 2025
API_KEY=votre_cle_secrete_ici
```

### 4. Lancer la suite de tests (Validation de l'intégrité)

```powershell
pytest -v
```
> **128 tests unitaires, fonctionnels et E2E exécutés en ~1.5 seconde.**

### 5. Tester l'assistant en direct (Console interactive)

Une console interactive simulant le dialogue réel est disponible :
```powershell
python scripts/chat.py
```
```text
======================================================================
🤖 Personal Assistant Hub - Console Interactive
   Tapez votre demande en langage naturel (ou 'exit' pour quitter)
======================================================================

Vous > Qu'est-ce qu'on mange ce soir ?
Assistant > D'après le planning des repas pour ce soir, vous avez prévu : Quiche aux poireaux.
         [Intention: get_meal_plan | Confiance: 95%]

Vous > Ajoute les ingrédients à ma liste de courses sauf les lardons
Assistant > Ingrédients de 'Quiche aux poireaux' ajoutés à la liste d'attente : Poireaux, Pâte brisée, Crème fraîche, Œufs. (Exclu(s) : lardons).
         [Intention: add_shopping_item | Confiance: 95%]

Vous > Il me reste quoi à acheter au rayon Légumes ?
Assistant > Au rayon Légumes, il vous reste 1 article(s) à acheter : Poireaux.
         [Intention: get_shopping_list | Confiance: 95%]
```

> 💡 **Mode Démo / Évaluation Recruteur (*Zero-Config*) :**  
> En l'absence de fichier d'identifiants Google (`service_account.json`), l'application bascule gracieusement en **mode simulation / mock hors-ligne**. Vous pouvez ainsi cloner le dépôt, lancer `scripts/chat.py` ou le serveur FastAPI et tester immédiatement la robustesse du moteur NLU, le routage d'intentions et la mémoire conversationnelle sans aucune configuration externe.


### 6. Lancer le serveur API

```powershell
uvicorn app.main:app --reload --port 8000
```
La documentation OpenAPI interactive (Swagger UI) est disponible sur **`http://127.0.0.1:8000/docs`**.

---

## 👨‍💻 À propos de l'Auteur

**Alexis Lévêque** — *Développeur Backend Web (PHP / Symfony & Python)*
* 📍 La Rochelle, France
* 🔗 [LinkedIn](https://www.linkedin.com/in/alexis-l%C3%A9v%C3%AAque-04b38b1b2/) • [GitHub](https://github.com/Alexisleveque-OC)
* 💡 *Engagé pour le code propre, la maintenabilité, l'architecture modulaire et les tests automatisés.*
