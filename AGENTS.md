# Directives & Mémoire Permanente du Projet (AGENTS.md)

Ce document est la source de vérité absolue pour tout agent d'IA intervenant sur le projet **Personal Assistant Hub**.

---

## 1. Stack Technique
* **Langage :** Python 3.12+
* **Framework Web :** FastAPI (avec Pydantic v2 pour la validation stricte)
* **Serveur ASGI :** Uvicorn
* **Test Runner :** Pytest avec HTTPX (`TestClient`)
* **Gestionnaire d'environnement :** Python venv (`.venv`)

---

## 2. Architecture Modulaire : Pattern Connecteurs
L'application suit une séparation stricte des responsabilités :
```
personal-assistant-hub/
├── app/
│   ├── main.py              # Point d'entrée FastAPI & routes
│   ├── config.py            # Paramètres et variables d'environnement
│   ├── core/                # Logique centrale & Moteur d'intentions
│   │   ├── intent_parser.py # Analyse NLU / classification d'intention
│   │   └── models.py        # Modèles de données Pydantic (contrats)
│   └── connectors/          # Connecteurs externes (isolés et interchangeables)
│       ├── base.py          # Interface commune des connecteurs
│       ├── sheets/          # Google Sheets (Budget, Repas/Courses)
│       ├── tasks/           # Google Tasks
│       ├── gmail/           # Lecture & récapitulatif Gmail
│       └── smart_home/      # Domotique (prise connectée)
├── tests/                   # Tests unitaires et fonctionnels
│   ├── test_health.py
│   └── test_intent_parser.py
├── .gitignore
├── AGENTS.md                # Mémoire permanente (ce fichier)
├── SPEC.md                  # Cahier des charges et backlog fonctionnel
└── requirements.txt
```

---

## 3. Commandes Fondamentales (Windows PowerShell)

* **Activer l'environnement virtuel :**
  ```powershell
  .\.venv\Scripts\Activate.ps1
  ```
* **Lancer les tests unitaires (Boucle de rétroaction) :**
  ```powershell
  .\.venv\Scripts\pytest -v
  ```
* **Lancer le serveur de développement :**
  ```powershell
  .\.venv\Scripts\uvicorn app.main:app --reload --port 8000
  ```

---

## 4. Règles d'Or de Développement Agentique

1. **Test-First & Feedback Loops :** Toujours écrire ou mettre à jour un test pour chaque nouvelle fonctionnalité. Exécuter `pytest` après chaque modification. Si un test échoue, analyser la trace d'erreur et corriger de façon autonome avant de solliciter l'utilisateur.
2. **Hygiène Git & Stratégie de Branches :**
   * **Branche `main` :** Protégée, toujours déployable. Aucun commit direct pour les features.
   * **Stratégie de branches :** Chaque fonctionnalité ou correction est développée sur une branche dédiée (`feat/<feature-name>`, `fix/<bug-name>`) ou sur `develop`.
   * **Pull Request / Merge Request (PR/MR) :** Fusion vers `main` uniquement après validation de la suite de tests (`pytest` à 100% vert) et relecture.
   * **Sécurité :** Ne JAMAIS commiter de fichiers sensibles (`.env`, `credentials.json`, `token.json`, `.venv`).
   * **Commits :** Atomiques et explicites au format Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `refactor:`).
3. **Typage et Contrats :** Tout modèle de données entrant ou sortant doit être typé via Pydantic. Pas de dictionnaires bruts arbitraires non validés.
4. **Indépendance des Connecteurs :** Chaque connecteur dans `app/connectors/` doit pouvoir fonctionner avec des mocks en mode hors-ligne ou lors des tests.
5. **Intégration Continue (CI) :** Les tests doivent tourner automatiquement sur GitHub Actions à chaque PR/MR.
6. **Roadmap par Feature & Validation Pas-à-Pas (Human-in-the-Loop) :**
   * Pour chaque fonctionnalité (`feat/*`), un fichier `ROADMAP.md` dédié doit être créé à la racine du projet.
   * La roadmap détaille les étapes d'implémentation de manière ordonnée et progressive.
   * **Chaque étape doit être validée manuellement et explicitement par l'utilisateur** et afficher 100% de tests au vert avant de passer à la suivante.
   * **Test d'intégration final :** À la fin de chaque feature, un test d'intégration complet (E2E) doit être mis en place pour valider le flux de bout en bout et garantir la pérennité de la solution dans le temps.
