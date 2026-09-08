# Personal Assistant Hub 🧠⚡

Un hub d'orchestration personnel intelligent, modulaire et autonome pour connecter le langage naturel (voix / texte) à son quotidien numérique :
* 🥗 **Repas & Liste de Courses :** Consultation du menu de la semaine et alimentation de la liste d'achats (Google Sheets unifié).
* 💰 **Budget Personnel :** Consultation des soldes restants et enregistrement rapide de dépenses catégorisées (Google Sheets).
* ✅ **Google Tasks :** Rappels et gestion des tâches du jour.
* 📧 **Gmail :** Résumés et détection des e-mails importants.
* 🔌 **Domotique :** Contrôle d'équipements connectés (prises, etc.).

---

## Architecture

L'application repose sur le **Pattern Connecteurs** :
* Un **Core** qui analyse les requêtes en langage naturel (intentions & paramètres).
* Des **Connecteurs isolés** dans `app/connectors/`, testables indépendamment.

```
personal-assistant-hub/
├── app/
│   ├── main.py              # Application FastAPI & endpoints REST
│   ├── config.py            # Configuration par variables d'environnement
│   ├── core/                # Moteur d'intentions et modèles Pydantic
│   └── connectors/          # Connecteurs (Sheets, Tasks, Gmail, Domotique)
├── tests/                   # Suite de tests unitaires et fonctionnels (Pytest)
├── AGENTS.md                # Mémoire permanente & directives de développement
└── SPEC.md                  # Cahier des charges et backlog évolutif
```

---

## Installation & Démarrage

### 1. Prérequis
* Python 3.12+
* Git

### 2. Initialisation

```bash
# Cloner le dépôt
git clone https://github.com/Alexisleveque-OC/personal-assistant-hub.git
cd personal-assistant-hub

# Créer et activer l'environnement virtuel
python -m venv .venv
.\.venv\Scripts\activate   # Sur Windows (PowerShell)
# source .venv/bin/activate  # Sur Linux/macOS

# Installer les dépendances
pip install -r requirements.txt
```

### 3. Lancer les tests

```bash
pytest -v
```

### 4. Démarrer l'API en local

```bash
uvicorn app.main:app --reload --port 8000
```
La documentation interactive Swagger est alors accessible à l'adresse : **http://127.0.0.1:8000/docs**.
