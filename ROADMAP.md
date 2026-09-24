# Roadmap Feature : Déploiement Continu (CI/CD) & Hébergement Cloud 24h/24 (`feat/cicd-cloud-deployment`)

> **Règles d'or (AGENTS.md) :**
> - Chaque étape doit être validée **manuellement et explicitement par l'utilisateur** avant de passer à la suivante.
> - La suite de tests automatisés (`pytest`) doit être à **100% au vert** à chaque étape.
> - Tout nouveau code de production est développé en **TDD Strict** (Phase Rouge $\rightarrow$ Phase Verte $\rightarrow$ Refactor).
> - À la fin de la feature, un **test d'intégration complet** valide la pérennité du pipeline.

---

## Vue d'ensemble des Étapes

| Étape | Description | Statut | Validation Utilisateur | Tests Automatisés |
| :--- | :--- | :---: | :---: | :---: |
| **Étape 1** | Conteneurisation de production (`Dockerfile`, `.dockerignore`) & Port dynamique `$PORT` | 🟢 Validé | ✅ Validé par l'utilisateur | ✅ Tests structurels & build Docker validés |
| **Étape 2** | Support des secrets Cloud pour Google Sheets (`GOOGLE_SERVICE_ACCOUNT_INFO` en env var) | 🟢 Validé | ✅ Validé par l'utilisateur | ✅ Tests TDD validés (`test_cloud_credentials.py`) |
| **Étape 3** | Pipeline GitHub Actions de Déploiement Continu automatique à chaque MR vers `main` | 🟢 Validé | ✅ Validé par l'utilisateur | ✅ Workflow validé (`.github/workflows/deploy.yml`) |
| **Étape 4** | Guide de mise en service Cloud pas-à-pas (`docs/GUIDE_DEPLOIEMENT_CLOUD.md`) | 🟢 Validé | ✅ Validé par l'utilisateur | ✅ Documentation rédigée et intégrée |
| **Étape 5** | Test d'intégration global & validation de non-régression | 🟢 Validé | ✅ Validé par l'utilisateur | ✅ 100% tests verts (177 tests) |

---

## Détail des Étapes

### 🟢 Étape 1 : Conteneurisation de production & Port dynamique `$PORT`
* **Objectif :** Rendre l'application exécutable dans n'importe quel environnement Cloud moderne (Google Cloud Run, Render, Koyeb, Docker) sans dépendance locale.
* **Livrables & Réalisations :**
  * `Dockerfile` de production basé sur `python:3.12-slim`, utilisateur non-root `appuser` (sécurité Cloud).
  * `.dockerignore` strict excluant `.env`, `credentials.json`, `.venv`, `.git` et logs.
  * Prise en compte dynamique de la variable `$PORT` (compatible Cloud Run, Render, Railway, Koyeb).
  * Tests automatisés dans `tests/test_docker_and_deployment_config.py` (100% au vert).
  * Build et exécution réels validés avec succès sur le moteur Docker local.

---

### 🟢 Étape 2 : Support des secrets Cloud sans fichier physique (`GOOGLE_SERVICE_ACCOUNT_INFO`)
* **Objectif :** Permettre au connecteur Google Sheets de s'authentifier dans le Cloud sans devoir déposer un fichier physique `credentials.json` sur le serveur.
* **Livrables & Réalisations :**
  * Support de `GOOGLE_SERVICE_ACCOUNT_INFO` dans `app/config.py`.
  * Décodage transparent du JSON brut ou encodé en base64 via `gspread.service_account_from_dict()` dans `app/connectors/sheets/meals_connector.py`.
  * Préservation de la rétrocompatibilité avec le fichier local `credentials.json`.
  * Tests unitaires TDD validés dans `tests/test_cloud_credentials.py` (100% au vert).

---

### 🟢 Étape 3 : Pipeline GitHub Actions de Déploiement Continu (Auto-deploy on MR)
* **Objectif :** Déployer automatiquement l'application dès qu'une Merge Request / PR est fusionnée dans `main`.
* **Livrables & Réalisations :**
  * Création de `.github/workflows/deploy.yml` déclenché uniquement sur `push` vers `main`.
  * Dépendance stricte sur l'exécution réussie de la suite de tests (`pytest` à 100% vert).
  * Support double cible : Google Cloud Run (niveau gratuit permanent GCP) et Webhook universel (Render / Koyeb).
  * Gestion bienveillante si les secrets ne sont pas encore renseignés (message informatif sans échec bloquant).
  * Tests automatisés validant la configuration du pipeline.

---

### 🟢 Étape 4 : Guide de mise en service Cloud pas-à-pas
* **Objectif :** Accompagner l'utilisateur pour connecter son compte Google Cloud ou Render et configurer les secrets en toute sérénité.
* **Livrables réalisés :**
  * Guide illustré et exhaustif dans `docs/GUIDE_DEPLOIEMENT_CLOUD.md`.
  * Explication pas-à-pas des secrets à renseigner dans GitHub (`API_KEY`, `SPREADSHEET_MEALS_SHOPPING_ID`, `GOOGLE_SERVICE_ACCOUNT_INFO`).
  * Déploiement guidé pour Google Cloud Run (gratuit 2M requêtes/mois) et Render (clé en main).

---

### 🟢 Étape 5 : Test d'intégration global & validation finale
* **Objectif :** Valider l'ensemble de la chaîne avant la fusion finale.
* **Résultats :**
  * Suite complète de tests exécutée à 100% au vert (177 tests passés).
  * Validations des conteneurs, configurations CI/CD, parsing des credentials et de l'ensemble des flux vocaux et connecteurs.
  * Prêt pour la Pull Request / Merge Request vers `develop` et `main`.
