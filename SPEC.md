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

- [x] **Phase 1 : Socle & Pratiques**
  - [x] Création des fichiers de contexte (`AGENTS.md`, `SPEC.md`, `.gitignore`)
  - [ ] Configuration de l'environnement Python (`.venv`, `requirements.txt`)
  - [ ] Architecture modulaire de base (`app/main.py`, `app/core/`, `app/connectors/`)
  - [ ] Tests unitaires initiaux et validation de la boucle de rétroaction
  - [ ] Initialisation du dépôt Git & push vers `origin`
- [ ] **Phase 2 : Connecteur Repas & Courses (Google Sheets)**
  - [ ] Modélisation des données repas & courses
  - [ ] Mock local pour tester sans dépendre de Google API en phase de dev
  - [ ] Intégration Google Sheets API / Service Account
  - [ ] Tests automatisés
- [ ] **Phase 3 : Connecteur Budget (Google Sheets)**
  - [ ] Modélisation des dépenses & catégories
  - [ ] Calculs de soldes
  - [ ] Tests automatisés
- [ ] **Phase 4 : Google Tasks & Gmail**
- [ ] **Phase 5 : Domotique & Interfaces Vocales (Android / Alexa)**
