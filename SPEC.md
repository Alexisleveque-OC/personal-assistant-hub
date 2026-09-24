# Spécifications & Backlog (SPEC.md)

Ce document décrit la vision produit, les cas d'usage et l'avancement des fonctionnalités du **Personal Assistant Hub**.

---

## 1. Vision du Produit
Un hub d'assistance unifié capable de recevoir des requêtes en langage naturel (voix ou texte) et d'agir sur le quotidien de l'utilisateur :
1. **Gestion du Budget :** Consulter le solde restant, ajouter des dépenses catégorisées.
2. **Gestion des Repas & Courses :** Consulter le menu du jour, ajouter des ingrédients à la liste de courses (même Google Sheet multi-onglets).
3. **Google Tasks :** Consulter les tâches du jour, ajouter un rappel/tâche.
4. **Gmail :** Résumer les e-mails récents jugés importants.
5. **Domotique :** Piloter une prise connectée (allumer / éteindre / état).

---

## 2. Connecteurs & Spécifications Métier

### A. Connecteur Google Sheets : Repas & Courses (Même Sheet)
* **Structure :** Un seul classeur Google Sheets avec plusieurs onglets (ex: "Repas", "Courses").
* **Évolutivité :** Le schéma du tableau doit pouvoir accueillir de nouvelles colonnes sans casser l'application.
* **Intentions associées :**
  * `get_meal_plan` (ex: "Qu'est-ce qu'on mange ce soir ?")
  * `add_shopping_item` (ex: "Ajoute du lait et des œufs à la liste de courses")
  * `get_shopping_list` (ex: "Donne-moi la liste de courses")

### B. Connecteur Google Sheets : Budget
* **Structure :** Classeur dédié au suivi financier.
* **Intentions associées :**
  * `get_budget_balance` (ex: "Combien il me reste pour les courses ce mois-ci ?")
  * `log_expense` (ex: "J'ai acheté pour 45€ de bricolage")

### C. Connecteur Google Tasks
* **Intentions associées :**
  * `add_task` (ex: "Rappelle-moi d'appeler le médecin demain")
  * `list_tasks` (ex: "Quelles sont mes tâches aujourd'hui ?")

### D. Connecteur Gmail
* **Intentions associées :**
  * `summarize_important_emails` (ex: "Ai-je des mails importants aujourd'hui ?")

### E. Connecteur Domotique (Prise Connectée)
* **Intentions associées :**
  * `toggle_device` / `get_device_status`

---

## 3. Feuille de Route / Backlog d'Implémentation

- [x] **Phase 1 : Socle & Pratiques (Terminée)**
  - [x] Création des fichiers de contexte (`AGENTS.md`, `SPEC.md`, `.gitignore`)
  - [x] Configuration de l'environnement Python (`.venv`, `requirements.txt`)
  - [x] Architecture modulaire de base (`app/main.py`, `app/core/`, `app/connectors/`)
  - [x] Tests unitaires initiaux et validation de la boucle de rétroaction
  - [x] Initialisation du dépôt Git & push vers `origin`
- [x] **Phase 2 : Connecteur Repas & Courses - Google Sheets (Terminée)**
  - [x] Modélisation des données repas & courses
  - [x] Mock local pour tester sans dépendre de Google API en phase de dev
  - [x] Intégration Google Sheets API / Service Account
  - [x] Tests automatisés (128 tests au vert, unitaires + E2E)
  - [x] Intégration Apps Script (`meal-planner`) et synchronisation Liste d'Attente
- [x] **Phase 3 : Interface Mobile & Entrées Vocales - Android PWA (Terminée)**
  - [x] Exposition et sécurisation de l'API (`API_KEY`) pour accès mobile
  - [x] Interface utilisateur Web PWA vocale avec micro réactif et TTS
  - [x] Logo personnalisé Monstera haute définition avec marge de respiration de 5%
  - [x] Icônes Android PWA adaptatives (maskable, standard, touch icon)
  - [x] Mode hors-ligne, Service Worker v3 et gestion du cache PWA
  - [x] Validation sur smartphone en conditions réelles et tests E2E
- [x] **Phase 3 bis : Conteneurisation & CI/CD Cloud 24h/24 (Terminée)**
  - [x] Conteneurisation Docker de production (`python:3.12-slim`, non-root, `$PORT` dynamique)
  - [x] Support des secrets Cloud pour Google Sheets (`GOOGLE_SERVICE_ACCOUNT_INFO`)
  - [x] Pipeline GitHub Actions de déploiement automatique sur chaque MR fusionnée dans `main`
  - [x] Guide de déploiement Cloud pas-à-pas (`docs/GUIDE_DEPLOIEMENT_CLOUD.md`)
  - [x] *Évolution prévue (Backlog futur) :* Double environnement automatique avec préproduction (staging) branchée sur `develop` et production branchée sur `main` (deux applications distinctes pour tester avant la mise en production).
- [ ] **Phase 4 : Tâches & Mails - Google Tasks & Gmail**
  - [ ] Connecteur Google Tasks (synthèse des tâches du jour, ajout vocal de tâche avec échéance)
  - [ ] Connecteur Gmail (analyse des mails non lus, filtrage du bruit, synthèse des messages importants)
  - [ ] Tests automatisés
- [ ] **Phase 5 : Connecteur Budget - Google Sheets**
  - [ ] Modélisation des dépenses & catégories budgétaires
  - [ ] Consultation des soldes restants par catégorie
  - [ ] Enregistrement des dépenses au fil de l'eau
  - [ ] Calculs de soldes & alertes de dépassement
  - [ ] Tests automatisés
- [ ] **Phase 6 : Domotique & Alexa**
  - [ ] Connecteur prise connectée (allumer / éteindre / statut)
  - [ ] Intégration Skill Alexa pour les enceintes du domicile


