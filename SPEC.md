# Spécifications & Backlog Produit (SPEC.md)

Ce document décrit la vision produit, l'architecture des modules métier et la feuille de route d'implémentation du **Personal Assistant Hub**.

---

## 1. Vision du Produit

Un **assistant personnel unifié du quotidien**, capable d'assister l'utilisateur sur ses sphères **personnelle et professionnelle**, via des interfaces multiples et fluides (PWA mobile vocale, enceintes connectées Amazon Echo/Alexa, messagerie Telegram).

### Piliers Fondamentaux
1. **Intelligence Naturelle & Conversationnelle :** Remplacement de la rigidité des expressions régulières par un cerveau LLM fluide capable de gérer le dialogue multi-tours (clarifications, suggestions, confirmations bienveillantes).
2. **Réactivité Temps Réel (< 1 à 2 secondes) :** Architecture asynchrone découplée (mise en cache mémoire RAM au démarrage et écritures réseau en arrière-plan) pour garantir des réponses orales quasi-instantanées.
3. **"Second Cerveau" & Mémoire Long-terme :** Déchargement mental immédiat (boîte à idées dev, projets, notes libres) et apprentissage progressif du profil utilisateur (goûts alimentaires, centres d'intérêt, style de vie) pour adapter le ton et la pertinence du discours.
4. **Chronique Matinale Audio (Mini-Podcast Quotidien) :** Briefing dynamique chaque matin (via Edge-TTS), agrégeant de façon modulaire les données disponibles (repas du jour, tâches prioritaires, sport, actualités ciblées).
5. **Cloisonnement Strict Perso vs Pro :** Séparation hermétique des accès, des tokens d'API et des contextes de données.

---

## 2. Modules & Spécifications Métier

### A. Repas & Courses (Google Sheets) - [🟢 Opérationnel]
* **Rôle :** Consultation du planning annuel dynamique (`repas <année>`), interrogation du carnet de recettes (>1000 recettes), alimentation de la liste de courses via `Liste_Attente` et catégorisation dynamique par rayons.
* **Statut :** Connecteur `MealsShoppingConnector` finalisé, validé par 128 tests automatisés (Mock + E2E Live).

### B. Moteur Conversationnel LLM (Google Gemini) & Réactivité Temps Réel - [🟢 Opérationnel]
* **Rôle :** Passerelle NLU intelligente, réflexive et ultra-rapide remplaçant la rigidité des expressions régulières.
* **Fonctionnalités clés :**
  * Intégration de Google Gemini Flash avec auto-découverte dynamique du dernier modèle stable et gestion de cooldown sur erreur 429.
  * Structured Outputs (Pydantic) pour mapper précisément les intentions et les paramètres métier.
  * Gestion du dialogue multi-tours naturel (mémoire de session, clarifications ciblées de rayon, anaphores contextuelles).
  * Tolérance avancée aux tirets, accents, ponctuations et pluriels dans la recherche de recettes.
  * Optimisation de latence (< 1-2s) : préchauffage du cache mémoire au boot (`warmup_cache`) et écritures Google Sheets asynchrones en arrière-plan (`BackgroundTasks`).
  * Repli local déterministe automatique en cas de panne réseau ou de quota dépassé.
* **Statut :** Finalisé, validé par 208 tests automatisés (Unitaires + E2E) et validé sur smartphone PWA.

### C. Mémoire Long-Terme & "Second Cerveau" (Notes, Idées & Profil)
* **Rôle :** Permettre à l'utilisateur de parler librement à son assistant pour décharger son esprit et enrichir sa connaissance personnelle.
* **Fonctionnalités clés :**
  * **Boîte à idées / Notes libres :** Capture vocale instantanée de pensées, idées de dev, projets ou mémos stockés dans une base locale structurée (SQLite).
  * **Profil Utilisateur dynamique (`profile.json`) :** Extraction automatique des préférences (ex: aliments détestés ou favoris, centres d'intérêt tech, objectifs sportifs).
  * **Injection Persona :** Enrichissement du prompt système pour rendre l'assistant complice, personnalisé et proactif.

### D. Chronique Matinale Audio (Mini-Podcast Quotidien)
* **Rôle :** Génération quotidienne automatisée (job planifié à 7h30) d'une chronique audio de 2 minutes.
* **Fonctionnalités clés :**
  * Agrégation modulaire des blocs disponibles : menu du jour (repas), tâches prioritaires, séance de sport, météo et actualités ciblées (flux RSS spécialisés).
  * Scénarisation du script par le LLM adapté au profil d'Alexis.
  * Synthèse vocale française ultra-naturelle via Microsoft Edge-TTS (fichiers MP3 sans coût d'API).
  * Diffusion sur la PWA ou en note vocale sur Telegram.

### E. Connecteurs Perso : Google Tasks & Gmail Perso
* **Google Tasks :** Consultation et ajout de tâches ou rappels du quotidien.
* **Gmail Perso :** Détection et synthèse des e-mails personnels critiques (suivi de livraison de colis, factures, alertes urgentes).

### F. Connecteur Budget (Google Sheets)
* **Rôle :** Suivi financier sur le classeur Google Sheets dédié.
* **Intentions associées :** Consultation du solde restant par catégorie, saisie vocale rapide de dépenses avec catégorisation automatique.

### G. Interfaces Vocales & Messageries (Alexa Skill & Bot Telegram)
* **Amazon Alexa (Enceintes Echo) :**
  * Custom Skill Alexa avec slot universel (`AMAZON.SearchQuery`).
  * Endpoint Webhook sécurisé FastAPI (`/api/v1/integrations/alexa`) pour utiliser le même moteur NLU et les mêmes connecteurs que la PWA.
* **Passerelle Telegram :**
  * Bot interactif pour échanger par messages texte ou recevoir et envoyer des notes vocales en mobilité.

### H. Connecteurs Professionnels (Mails Pro, Jira & Trello)
* **E-mails Pro (Google Workspace / Outlook) :** Résumé des échanges importants et réunions de la journée.
* **Jira :** Consultation des tickets assignés dans le sprint, imputation rapide de temps passé (`log_work_time`).
* **Trello :** Suivi et déplacement de cartes sur les tableaux de bord professionnels.

### I. Domotique & Environnement
* **Rôle :** Pilotage d'équipements connectés (prises, lumières, scènes via API Tuya / Home Assistant).

---

## 3. Feuille de Route / Backlog d'Implémentation

- [x] **Phase 1 : Socle & Pratiques (Terminée)**
  - [x] Création des fichiers de contexte (`AGENTS.md`, `SPEC.md`, `.gitignore`)
  - [x] Configuration de l'environnement Python (`.venv`, `requirements.txt`)
  - [x] Architecture modulaire de base (`app/main.py`, `app/core/`, `app/connectors/`)
  - [x] Tests unitaires initiaux et validation de la boucle de rétroaction
  - [x] Initialisation du dépôt Git & push vers `origin`
  - [x] Migration propre vers l'environnement Linux WSL (Python 3.12.14, `.venv`, commandes Bash)

- [x] **Phase 2 : Connecteur Repas & Courses - Google Sheets (Terminée)**
  - [x] Modélisation des données repas & courses
  - [x] Authentification Service Account & résolution d'année dynamique (`repas 2026`)
  - [x] Schéma de détection de dérive (Schema Drift)
  - [x] Gestion de la liste d'attente (`Liste_Attente`) et catalogues de rayons
  - [x] Intégration Apps Script (`meal-planner`) et synchronisation Liste d'Attente
  - [x] 128 tests automatisés (Unitaires + E2E Live) à 100% au vert

- [x] **Phase 3 : Interface Mobile & Entrées Vocales - Android PWA (Terminée)**
  - [x] Exposition et sécurisation de l'API (`API_KEY`) pour accès mobile
  - [x] Interface utilisateur Web PWA vocale avec micro réactif et TTS
  - [x] Logo personnalisé Monstera haute définition avec marge de respiration de 5%
  - [x] Icônes Android PWA adaptatives (maskable, standard, touch icon)
  - [x] Mode hors-ligne, Service Worker v4 et gestion du cache PWA avec auto-rechargement
  - [x] Validation sur smartphone en conditions réelles et tests E2E

- [x] **Phase 3 bis : Conteneurisation & CI/CD Cloud 24h/24 (Terminée)**
  - [x] Conteneurisation Docker de production (`python:3.12-slim`, non-root, `$PORT` dynamique)
  - [x] Support des secrets Cloud pour Google Sheets (`GOOGLE_SERVICE_ACCOUNT_INFO`)
  - [x] Pipeline GitHub Actions de déploiement automatique sur chaque MR fusionnée dans `main`
  - [x] Guide de déploiement Cloud pas-à-pas (`docs/GUIDE_DEPLOIEMENT_CLOUD.md`)

- [x] **Phase 4 : Moteur Conversationnel LLM (Google Gemini) & Performance (< 1-2s) - (Terminée)**
  - [x] Client LLM avec auto-découverte du dernier modèle Flash stable (`gemini-3.8-flash`) et cooldown sur 429
  - [x] Chaîne de repli de résilience et bascule locale transparente
  - [x] Dialogue multi-tours & Structured Outputs (clarification des rayons, confirmation de recettes)
  - [x] Cache mémoire RAM au boot du serveur pour les catalogues de données (`warmup_cache`)
  - [x] Écritures Google Sheets asynchrones en arrière-plan (`BackgroundTasks`) pour retour vocal immédiat
  - [x] Tolérance avancée aux recettes (tirets, accents, pluriels, nom officiel canonique)

- [ ] **Phase 5 : Mémoire Long-terme & "Second Cerveau"**
  - [ ] Stockage local SQLite pour la boîte à idées et notes libres (catégories, tags, date)
  - [ ] Modélisation et persistance du profil utilisateur (`profile.json` : goûts, centres d'intérêt)
  - [ ] Intention `capture_note` et mise à jour dynamique du persona de l'assistant

- [ ] **Phase 6 : Chronique Matinale Audio (Mini-Podcast Quotidien)**
  - [ ] Agrégateur modulaire de données du matin (repas, tâches, profil, RSS)
  - [ ] Prompt de scénarisation de chronique matinale
  - [ ] Moteur de synthèse vocale locale Edge-TTS (génération de MP3)
  - [ ] API de distribution (audio pour PWA et déclenchement planifié)

- [ ] **Phase 7 : Connecteurs Perso (Google Tasks & E-mails Gmail)**
  - [ ] Intégration Google Tasks API (consultation et création de tâches)
  - [ ] Connecteur Gmail (lecture et récapitulatif des notifications importantes)
  - [ ] Tests automatisés dédiés

- [ ] **Phase 8 : Connecteur Budget (Google Sheets)**
  - [ ] Modélisation des dépenses et catégories sur le classeur financier
  - [ ] Calculs de soldes restants et saisie de dépenses
  - [ ] Tests automatisés dédiés

- [ ] **Phase 9 : Interfaces Vocales & Messageries (Alexa Skill & Bot Telegram)**
  - [ ] Webhook FastAPI compatible avec le protocole Amazon Alexa Custom Skill
  - [ ] Routage direct des commandes vocales Alexa vers le moteur central
  - [ ] Passerelle bot Telegram (texte et messages vocaux entrants/sortants)

- [ ] **Phase 10 : Connecteurs Professionnels (Mails Pro, Jira & Trello)**
  - [ ] Connecteur Jira (lecture des tickets et logging de temps)
  - [ ] Connecteur Trello (lecture et déplacement de cartes)
  - [ ] Connecteur e-mails pro avec isolation stricte des secrets

- [ ] **Phase 11 : Domotique (Prises connectées & Scénarios)**
  - [ ] Intégration des APIs d'équipements connectés
  - [ ] Intentions de commande et de statut (`toggle_device`, `get_device_status`)

