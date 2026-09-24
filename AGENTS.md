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

0. **Règle Suprême - Challenger Technique & Gardien des Bonnes Pratiques :**
   * L'agent n'est JAMAIS un exécutant aveugle ou passif.
   * Si l'utilisateur propose une direction sous-optimale, une mauvaise pratique, ou une solution risquant d'introduire de la dette technique ou des bugs, l'agent **a l'obligation de la remettre en question**.
   * L'agent doit initier l'échange, expliquer avec pédagogie les compromis (avantages, inconvénients, impacts sur la maintenance) et proposer la meilleure alternative conforme à l'état de l'art.

1. **TDD Strict (Test-Driven Development) - Priorité Absolue :**
   * Tout développement de fonctionnalité DOIT obligatoirement suivre le cycle TDD :
     1. **Phase Rouge (Red) :** Écrire d'abord le test unitaire définissant le contrat, les paramètres attendus et le comportement cible. Exécuter `pytest` et constater que le test échoue pour la bonne raison (fonction/méthode non implémentée).
     2. **Phase Verte (Green) :** Écrire le code de production minimal permettant de satisfaire le test et valider que `pytest` passe à 100% vert.
     3. **Phase Refactor :** Améliorer la lisibilité, le typage strict, la modularité et l'adhérence aux conventions, tout en conservant 100% des tests au vert.
   * Il est formellement interdit d'écrire du code de production avant d'avoir le test correspondant qui échoue.
   * Boucle de rétroaction autonome : exécuter `pytest` après chaque changement. En cas d'échec, analyser la trace d'erreur et corriger de façon autonome avant de solliciter l'utilisateur.
2. **Hygiène Git & Stratégie de Branches :**
   * **Branche `main` :** Protégée, toujours déployable. Aucun commit direct pour les features.
   * **Stratégie de branches :** Chaque fonctionnalité ou correction est développée sur une branche dédiée (`feat/<feature-name>`, `fix/<bug-name>`) ou sur `develop`.
   * **Pull Request / Merge Request (PR/MR) :** Fusion vers `main` uniquement après validation de la suite de tests (`pytest` à 100% vert) et relecture.
   * **Sécurité :** Ne JAMAIS commiter de fichiers sensibles (`.env`, `credentials.json`, `token.json`, `.venv`).
   * **Zéro Commit Sans Test & Validation Préalable :** Il est **strictement interdit** de commiter du code avant d'avoir exécuté les tests (`pytest`), vérifié que tout fonctionne à 100%, et permis à l'utilisateur de tester/valider. Les tests et les vérifications viennent **toujours avant** tout commit git.
   * **Commits :** Atomiques, explicites et séparés selon leur périmètre :
     * **Fichiers d'instructions agent (ex: `AGENTS.md`) :** Toujours isolés dans leurs propres commits et préfixés par `#AGENT : <message>`.
     * **Code de feature :** Toujours préfixés par `#PAH - <feature-tag> : <type>: <message>` (ex: `#PAH - shop connector : feat: ...`), combinant le tag de feature et le format Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `refactor:`).
3. **Typage et Contrats :** Tout modèle de données entrant ou sortant doit être typé via Pydantic. Pas de dictionnaires bruts arbitraires non validés.
4. **Indépendance des Connecteurs :** Chaque connecteur dans `app/connectors/` doit pouvoir fonctionner avec des mocks en mode hors-ligne ou lors des tests.
5. **Intégration Continue (CI) :** Les tests doivent tourner automatiquement sur GitHub Actions à chaque PR/MR.
6. **Roadmap par Feature & Validation Pas-à-Pas (Human-in-the-Loop) :**
   * Pour chaque fonctionnalité (`feat/*`), un fichier `ROADMAP.md` dédié doit être créé à la racine du projet.
   * La roadmap détaille les étapes d'implémentation de manière ordonnée et progressive.
   * **Chaque étape doit être validée manuellement et explicitement par l'utilisateur** et afficher 100% de tests au vert avant de passer à la suivante.
   * **Test d'intégration final :** À la fin de chaque feature, un test d'intégration complet (E2E) doit être mis en place pour valider le flux de bout en bout et garantir la pérennité de la solution dans le temps.
7. **Erreurs Explicites & Fail-Fast (Déboguabilité Maximale) :**
   * Ne JAMAIS étouffer ou masquer une erreur avec des retours silencieux (`try/except: pass` ou fallbacks masqués sans log).
   * Toujours lever des exceptions claires, typées et contextualisées : indiquer précisément la ressource manquante, le paramètre attendu (ex: l'année cible et le nom d'onglet attendu), et la liste des ressources disponibles.
   * Cette clarté permet à l'utilisateur de comprendre immédiatement l'action requise (ex: créer l'onglet manquant sur son Google Sheet) et à l'agent de corriger de façon chirurgicale sans suppositions.
8. **Mise en Cache Intelligente (Performance & Quotas API) :**
   * Les lectures coûteuses (notamment les appels à l'API Google Sheets pour les listes de courses, plannings et recettes) doivent intégrer une mise en cache en mémoire (TTL raisonnable, ex: 2 à 5 minutes).
   * Cela garantit des temps de réponse quasi-instantanés sur l'application mobile et préserve les quotas stricts de Google Cloud (limite de 60 requêtes/minute).
   * **Invalidation immédiate :** Toute opération d'écriture ou de mutation (ex: ajout d'articles, coche d'un article acheté, suppression, modification de repas) doit obligatoirement invalider le cache immédiatement pour préserver la cohérence absolue des données.
9. **Discipline de Fusion & Tests Manuels Utilisateur (Zéro Merge Prématuré) :**
   * Il est **strictement interdit** de fusionner une branche de fonctionnalité (`feat/*`) vers `develop` ou `main` de manière anticipée.
   * Tout nouveau développement reste cantonné sur sa branche dédiée (`feat/<name>`).
   * L'agent doit inviter l'utilisateur à faire ses tests manuels sur son interface, et **attendre son retour explicite** avant de procéder à la moindre fusion vers `develop` ou `main`.
