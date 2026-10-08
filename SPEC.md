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

### C. Module Sport & Running (SQLite, Mini-Coach Otis & Futur Otis Live Runner)
* **Rôle :** Suivi, planification et analyse des séances de course à pied et de renforcement, avec rôle de "mini-coach" motivant, protecteur contre les blessures (périostite) et futur compagnon de course en direct.
* **Fonctionnalités clés :**
  * **Base de Données Locale SQLite (`sport_sessions`, `sport_weekly_summaries`) :** Remplacement haute performance du Google Sheet historique (< 1 ms de latence, zéro quota API, requêtes et agrégations instantanées).
  * **Calculs de charge & volume :** Synthèse automatique du volume kilométrique, temps cumulé, Charge RPE ($\text{Durée} \times \text{RPE}$), nb séances de renfo, alerte sécurité (+10% max) et plafond conseillé pour S+1.
  * **Interactions vocales :** Consultation de séance (*« Qu'est-ce que j'ai comme séance aujourd'hui ? »*), enregistrement vocal d'une course ou séance de renfo (*« J'ai fait 30 min de renfo, ressenti 7 sur 10 »*), réajustement a posteriori (*« Otis, modifie le ressenti de ma course de dimanche à 9 sur 10 à cause de ma périostite »*), résolution de "ma dernière séance".
  * **Adaptation Dynamique de Charge & Protection Périostite :** Prise en compte immédiate des douleurs aux tibias/musculaires pour adapter à la baisse les sorties longues, éviter le dénivelé négatif et préconiser du repos actif ou renforcement soléaire.
  * **Otis Live Runner (Capacitor / Android Foreground Service) :** Suivi GPS en direct activé uniquement pendant l'effort (extinction à la fin de la séance pour préserver la batterie), annonces d'allures au kilomètre dans les écouteurs, dictée mains-libres pendant la course et pilotage de Spotify par la voix.
  * **Passerelles & Écosystème :** Ingestion directe de traces GPX/FIT, indépendance de Strava/Decathlon et compatibilité montres Garmin Connect.

### D. Moteur Vocal Haute-Fidélité, Mémoire Long-Terme & "Second Cerveau"
* **Rôle :** Permettre à l'utilisateur de parler librement et naturellement à son assistant avec une transcription sans faille, de décharger son esprit et d'apprendre continuellement de ses interactions.
* **Fonctionnalités clés :**
  * **Moteur Vocal Résilient & Anti-Coupure :** Détection de fin de parole intelligente (VAD configurable 1.5s - 2.5s pour laisser le temps d'hésiter), reconnaissance continue et mode push-to-talk.
  * **Pipeline STT Haute Fidélité :** Remplacement ou renforcement du Web Speech API par un pipeline audio direct serveur (Gemini Multimodal Audio ou Faster-Whisper avec lexique métier) pour éliminer les confusions phonétiques ("Otis" / "10", "3" / "Troyes").
  * **Déclenchement Mains-Libres & Annulation ("Undo") :** Détection du Wake Word "Otis" in-app et commande d'annulation immédiate de la dernière action.
  * **Second Cerveau Compartimenté (SQLite `notes`) :** Capture vocale instantanée et segmentation sémantique automatique par le LLM (🛠️ Idées dev, 🐛 Bugs & corrections, 💡 Réflexions, 🎯 Préférences/habitudes, 📋 Tâches). Filtrage instantané pour retrouver ses idées de code.
  * **Auto-Apprentissage Vocal Interactif (`user_learnings`) :** Capacité d'éduquer Otis à la voix (*« Attention là tu as compris Troyes alors que j'ai dit 3 »*), extraction autonome de la règle apprise et ré-injection dynamique dans le prompt système sans retoucher au code.
  * **Profil Utilisateur dynamique (`user_profile`) :** Extraction et persistance des préférences (objectifs sportifs hebdo, allures cibles, aliments favoris/exclus, centres d'intérêt tech).
  * **Journal Conversationnel & Audit :** Traçabilité complète des échanges (`conversation_logs`), capture des erreurs et bouton de feedback/réajustement (`conversation_feedbacks`).

### E. Connecteurs Organisationnels : Google Agenda & Google Tasks
* **Google Agenda (Google Calendar API) :**
  * Consultation des événements et rendez-vous du jour et du lendemain.
  * Rappels d'échéances et dates importantes à venir.
* **Google Tasks :**
  * Consultation et ajout rapide de tâches ou rappels du quotidien à la voix.
* **Gmail Perso :**
  * Détection et synthèse des e-mails personnels critiques (suivi de livraison de colis, factures, alertes urgentes).

### F. Chronique Matinale Audio (Mini-Podcast Quotidien Enrichi)
* **Rôle :** Génération quotidienne automatisée (job planifié à 7h30) d'un briefing audio complet de 2-3 minutes.
* **Fonctionnalités clés :**
  * **Agrégation modulaire 360° :** Météo du jour, événements de l'Agenda, tâches prioritaires du jour (Tasks), séance de sport planifiée (Running), menus déjeuner et dîner (Repas).
  * **Scénarisation du script par le LLM Gemini Flash :** Ton motivant, complice et personnalisé au profil d'Alexis.
  * **Synthèse vocale française Edge-TTS :** Génération de MP3 ultra-fluide sans coût d'API.
  * **Diffusion :** Écoute sur la PWA ou en note vocale Telegram.

### G. Connecteur Budget (Google Sheets)
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

- [x] **Phase 5 : Module Sport Running & Mini-Coach Otis (Google Sheets & Tracking) - (Terminée)**
  - [x] Modélisation et validation du classeur Google Sheets Running (séances, formules automatiques allure/vitesse, statut prévus vs réalisés, Km-Effort)
  - [x] Calculs et tableau de bord de charge & volume par semaine (km totaux, temps cumulé, allure moyenne, Charge RPE, alerte sécurité +10%)
  - [x] Connecteur backend `SportConnector` (lecture de la séance du jour/semaine, enregistrement vocal post-séance, mise à jour RPE/notes)
  - [x] Cerveau LLM Otis : analyse fine d'historique sur 4 semaines, conseils personnalisés et planification hebdomadaire proactive
  - [x] Interface PWA Running : dashboard visuel multi-échelles (Semaine/Mois/Année), jauges SVG, pop-up RPE tactile et comparateur de séances
  - [x] Gamification dopaminée : badges de pop-culture (Astérix, Le Seigneur des Anneaux, Brandon Sanderson), exploits mono-séance et records
  - [x] Passerelle de synchronisation webhooks Strava (`/api/v1/integrations/strava/webhook`, `/api/v1/sport/sync-activity`)
  - [x] Test d'intégration End-to-End (`test_complete_e2e_running_and_coach_otis_lifecycle`) et 342 tests automatisés à 100% au vert

- [x] **Phase 5 bis : Refactoring Modulaire Architectural (Terminée)**
  - [x] Étude comparative et pédagogique (FastAPI Domain-First vs Symfony MVC, tokens et maintenabilité)
  - [x] Extraction des dépendances et singletons dans `app/core/dependencies.py` (élimination des imports circulaires)
  - [x] Découpage en sous-routeurs FastAPI (`routers/system.py`, `routers/pwa.py`, `routers/meals.py`, `routers/mobile.py`, `routers/sport.py`, `routers/strava.py`)
  - [x] Extraction des handlers d'intentions (`handlers/meals_handler.py`, `handlers/sport_handler.py`, `handlers/assistant_handler.py`) pour alléger `/api/v1/interact`
  - [x] `app/main.py` ultra-épuré (< 85 lignes)
  - [x] Découpage modulaire des vues PWA front-end en modules ES6 (`app/static/js/views/*`, `app/static/app.js` < 200 lignes)
  - [x] Maintien permanent de 100% des tests au vert (342 tests) et tableau comparatif Avant/Après

- [x] **Phase 5 ter : Retours d'Expérience Utilisateur (Sport & Courses) - (Terminée)**
  - [x] **Sport - Historique des séances passées & prévues :** vue chronologique, badges colorés, accordéons avec grille métrique complète, programme et alertes blessures.
  - [x] **Sport - Historique & Synthèse des semaines :** totaux hebdomadaires, indicateurs d'évolution de charge, alerte sécurité Otis et accordéon des séances composantes.
  - [x] **Courses - Synchronisation en lot & Réinitialisation :** bouton "J'ai fini !" envoyant un batch groupé dans Google Sheets, bouton "Réinitialiser" pour le cycle du samedi, préservation des cases à cocher.
  - [x] 352 tests automatisés (Unitaires + E2E) à 100% au vert.

- [ ] **Phase 6 : Moteur Vocal Haute-Fidélité, Mémoire Long-terme & Journal Conversationnel**
  - [ ] **Ergonomie Vocale & VAD (Voice Activity Detection) :**
    - Résolution du problème de coupure prématurée lors des hésitations (délai de silence configurable 1.5s - 2.5s, reconnaissance continue).
    - Mode d'écoute push-to-talk ou bouton bascule avec compte à rebours visuel de silence.
  - [ ] **Pipeline STT Robuste & Pérenne (Fin des erreurs phonétiques) :**
    - Résolution définitive des confusions de transcription (ex: "Otis" pris pour "10", "RPE à trois" transcrit en "à Troyes", "renfort" vs "renforcement").
    - Pipeline audio direct vers backend (Gemini Multimodal Audio natif ou Faster-Whisper avec dictionnaire/lexique métier injecté) pour s'affranchir des faiblesses du Web Speech API navigateur.
    - Couche de normalisation phonétique et consignes de résilience sémantique dans le prompt système du LLM.
  - [ ] **Déclenchement Mains-Libres & Wake Word :**
    - Mode écoute continue "Wake Word" dans l'application ouverte (détection du mot-clé "Otis").
    - Raccourci 1-tap Android (Widget écran d'accueil avec démarrage d'écoute immédiat).
  - [ ] **Commande d'Annulation ("Undo") :**
    - Annulation vocale ou tactile de la dernière action exécutée en cas d'erreur de compréhension.
  - [ ] **Socle Données SQLite & Mémoire Long-terme :**
    - Base locale SQLite unifiée (`hub_data.db`) avec mode WAL.
    - **Second Cerveau Compartimenté (Segmentation Sémantique Automatique) :**
      - Capture intelligente de pensées et classification automatique par le LLM selon le contexte :
        - 🛠️ `dev_idea` : Idées de développement (*« À dev », « J'aimerais bien que ça fasse ça »*).
        - 🐛 `bug_report` : Corrections à apporter (*« Correction », « Bug », « Il y a un problème sur... »*).
        - 💡 `thought` : Idées libres, réflexions (*« Idée », « Penser à... »*).
        - 🎯 `preference` : Préférences et habitudes de vie (*« J'aime ça », « Je préfère... »*).
        - 📋 `task` : Tâches à réaliser (*« Il faut que je fasse ça », « J'ai ça à faire »*).
      - Consultation rapide et filtrage par segments dans la PWA pour retrouver instantanément ses idées à coder.
    - **Ingestion Multimodale Visuelle (Screenshots / Photos via Gemini Vision) :**
      - Envoi direct de captures d'écran (bugs UI, erreurs, code) ou de photos (hôtels, idées de vacances, livres, recettes).
      - Analyse automatique par Gemini Vision (`inlineData`) : extraction d'un résumé intelligent, identification du sujet et classification autonome dans le bon segment du Second Cerveau (`bug_report`, `dev_idea`, `voyage`, `cuisine`...).
      - Enregistrement immédiat dans `second_brain_notes` sans obliger Alexis à dicter ou détailler manuellement.
    - Profil utilisateur dynamique (`user_profile` : habitudes, objectifs, contraintes).
  - [ ] **Auto-Apprentissage Vocal & Évolution Autonome (In-Context Learning) :**
    - **Intention `teach_assistant` / Auto-Correction vocale :**
      - Capacité de corriger Otis oralement sans ouvrir le code (*« Attention là tu as compris Troyes alors que je t'ai dit 3 »*, *« Quand je dis X, je veux dire Y »*, *« Le quinoa va en épicerie »*).
      - Analyse autonome du dernier échange (`conversation_logs`), extraction de la leçon/règle par Gemini et persistance en base (`user_learnings`).
      - Rétro-correction immédiate de la dernière action erronée.
      - **Injection dynamique des règles apprises :** enrichissement du prompt système à chaque tour de parole. Otis s'adapte, mémorise vos expressions et s'améliore continuellement tout seul.
    - **Journal Conversationnel & Audit :**
      - Table `conversation_logs` : traçabilité de chaque échange (prompt brut, intention, paramètres, modèle LLM, latence, statut, trace d'erreur).
      - Table `conversation_feedbacks` : logs des corrections manuelles ou orales.
      - Vue "Journal & Feedback" dans la PWA.

- [ ] **Phase 6.5 : Migration Sport - Du Google Sheet vers la Base SQLite & Résolution Temporelle**
  - [ ] **Migration Base de Données Sport :**
    - Schéma relationnel `sport_sessions` et `sport_weekly_summaries` dans SQLite.
    - Script one-off de migration et d'aspiration complète de l'historique depuis le Google Sheet actif.
    - Connecteur backend `SqlSportConnector` garantissant une latence < 1 ms et la fin des quotas d'API Google.
    - Outil de sauvegarde et d'export de secours (CSV / JSON).
  - [ ] **Résolution Sémantique Temporelle ("Ma dernière séance") :**
    - Résolution contextuelle dynamique de "ma dernière séance", "mon dernier footing" ou "ma dernière séance de renfo" par interrogation de la dernière entrée réelle en base (au lieu de supposer à tort `date.today()`).
  - [ ] **Correctifs des Réponses Vocales & Formats de Dates :**
    - Suppression de la formulation hardcodée "Pour aujourd'hui..." lors de la consultation d'une séance passée ou future.
    - Remplacement des dates ISO brutes parlées ("2026-10-07") par des formulations orales naturelles ("du 7 octobre", "d'hier").
    - Support de l'infinitif ("modifier", "changer") et tolérance sur les déclinaisons de vocabulaire ("renfort", "renfo").

- [ ] **Phase 7 : Otis Live Runner - Coach Vocal Temps Réel, Traqueur GPS Natif & Contrôle Spotify**
  - [ ] **Tracking GPS Natif & Autonomie Totale (Capacitor / Android Foreground Service) :**
    - Activation d'un *Foreground Service* natif avec notification persistante dans la barre d'état **uniquement pendant la séance active** (*« Otis, lance ma séance »* ou bouton « Démarrer »).
    - Extinction automatique à l'arrêt : zéro impact sur la batterie en dehors des courses.
    - Élimination des intermédiaires tiers (indépendance totale de Strava et Decathlon Coach) : calcul précis de la distance (Haversine), vitesse instantanée, allure au km, dénivelé D+ et temps réel sans pause artificielle.
    - Stockage local de la trace (coordonnées GPS / format GPX/FIT) en base SQLite.
  - [ ] **Affichage Cartographique Interactif en Direct & Tracé GPS (Leaflet / OpenStreetMap) :**
    - Carte interactive intégrée dans la PWA Sport (Leaflet / tuiles OpenStreetMap légères et économes en bande passante).
    - Point GPS en direct avec tracé continu du parcours (polyline dynamique) pendant la séance.
    - Vue récapitulative post-course : tracé complet, dégradé de couleur selon l'allure (carte de rythme / splits kilométriques) et profil altimétrique.
  - [ ] **Programmation de Fractionné & Guidage Audio en Direct (Comme Decathlon Coach) :**
    - Création et planification de séances d'intervalles complexes : échauffement, répétitions fractionnées ($N \times$ temps/distance rapide + temps/distance de récupération), blocs au seuil et retour au calme.
    - **Audio cues & décompte dans les oreilles :** bips d'alerte, décompte 3-2-1 avant chaque changement de phase, annonces vocales d'objectifs (*« Accélère ! Bloc 2 sur 6, 400m à 4'10/km »*, *« Trottine, récupération 1 minute »*).
    - Régulateur d'allure vocal : alerte si vous partez trop vite ou trop lentement par rapport à l'allure cible.
    - Bilan audio automatique à la fin du fractionné avec moyennes par bloc.
  - [ ] **Checklist de Renforcement Dépliable (Validation Clic & Voix) :**
    - Liste d'exercices structurée et interactive (accordéon dépliable par groupe musculaire dans l'onglet Sport : gainage, fentes, renforcement mollet/soléaire/tibial pour la périostite).
    - **Double modalité de validation :**
      - Au clic tactile sur les cases à cocher de la PWA.
      - À la voix sans toucher le téléphone : *« Otis, coche le gainage planche »*, *« J'ai fait 3 séries de mollets sur une marche »*, *« Valide tous les exercices de renfo »*.
    - Persistance SQLite des exercices réalisés et intégration automatique dans le volume de renforcement de la semaine.
  - [ ] **Coach Vocal Temps Réel & Feedback Mains-Libres en Course :**
    - Alertes audio automatiques à chaque kilomètre : allure moyenne du dernier kilomètre, distance parcourue, reste à parcourir.
    - Écoute continue mains-libres dans les écouteurs : questionner Otis sur ses métriques à tout instant (*« Otis, j'en suis à combien ? »*, *« Quelle est mon allure moyenne ? »*) ou lui dicter des pensées/idées pour le Second Cerveau en courant.
  - [ ] **Module Protecteur Blessure & Adaptation Dynamique du Plan (Gestion Périostite) :**
    - Prise en compte immédiate des ressentis oraux de douleur en course ou au débrief (*« J'ai mal au tibia »*, *« Ma périostite me lance »*).
    - Ajustement automatique du plan de la semaine : allègement de la sortie longue du weekend (-30% à -50%), suppression temporaire du dénivelé négatif (D-) et du fractionné, proposition de cross-training (vélo) et de renforcement adapté (soléaire/tibial).
  - [ ] **Contrôle Musical Spotify Connect Mains-Libres :**
    - Connexion OAuth2 avec l'API Spotify Web / Spotify Connect.
    - Commandes vocales directes sans sortir le smartphone : *« Otis, mets ma playlist Running »*, *« Otis, morceau suivant »*, *« Otis, mets du son motivant »*.
  - [ ] **Passerelle Montres Connectées (Garmin Connect & Ingestion .FIT) :**
    - Ingestion et parsing des fichiers d'activité natifs `.FIT` de Garmin.
    - Architecture prête pour synchronisation API Garmin Connect dès acquisition d'une montre de running.

- [ ] **Phase 8 : Connecteurs Organisationnels (Google Agenda & Google Tasks)**
  - [ ] Intégration Google Calendar API (événements du jour, échéances, dates importantes)
  - [ ] Intégration Google Tasks API (consultation et création de tâches)
  - [ ] Connecteur Gmail (lecture et récapitulatif des notifications importantes)
  - [ ] Tests automatisés dédiés

- [ ] **Phase 9 : Chronique Matinale Audio (Mini-Podcast Quotidien Enrichi)**
  - [ ] Agrégateur modulaire universel du matin (Météo locale, Agenda du jour, Tâches prioritaires, Séance de sport prévue, Menus déjeuner & dîner, Profil)
  - [ ] Scénarisation dynamique par Gemini Flash
  - [ ] Moteur de synthèse vocale locale Edge-TTS (génération de MP3)
  - [ ] API de distribution (audio pour PWA et déclenchement planifié)

- [ ] **Phase 10 : Connecteur Budget (Google Sheets)**
  - [ ] Modélisation des dépenses et catégories sur le classeur financier
  - [ ] Calculs de soldes restants et saisie de dépenses
  - [ ] Tests automatisés dédiés

- [ ] **Phase 11 : Interfaces Vocales & Messageries (Alexa Skill & Bot Telegram)**
  - [ ] Webhook FastAPI compatible avec le protocole Amazon Alexa Custom Skill
  - [ ] Routage direct des commandes vocales Alexa vers le moteur central
  - [ ] Passerelle bot Telegram (texte et messages vocaux entrants/sortants)

- [ ] **Phase 12 : Connecteurs Professionnels (Mails Pro, Jira & Trello)**
  - [ ] Connecteur Jira (lecture des tickets et logging de temps)
  - [ ] Connecteur Trello (lecture et déplacement de cartes)
  - [ ] Connecteur e-mails pro avec isolation stricte des secrets

- [ ] **Phase 13 : Domotique (Prises connectées & Scénarios)**
  - [ ] Intégration des APIs d'équipements connectés
  - [ ] Intentions de commande et de statut (`toggle_device`, `get_device_status`)

---

## 4. Dette Technique & Refactoring Architectural (Planifié)

### Refactoring Modulaire de `app/main.py` (> 1200 lignes)
* **Constat :** `app/main.py` centralise actuellement la configuration FastAPI, les routes système, l'adaptateur mobile, le grand bloc d'aiguillage des intentions (`match parsed.intent`), les endpoints repas, sport, webhooks et la PWA. Cette concentration nuit à la lisibilité et à la maintenabilité.
* **Architecture cible (Clean Architecture & FastAPI Routers) :**
  1. **Découpage en APIRouters dédiés (`app/routers/`) :**
     * `routers/system.py` : routes de santé (`/health`, `/`), métriques LLM, préchauffage cache.
     * `routers/interact.py` : point d'entrée universel `/api/v1/interact` et analyse NLU `/api/v1/intent/parse`.
     * `routers/mobile.py` : adaptateur Android HTTP Shortcuts `/api/v1/mobile/interact`.
     * `routers/meals.py` : endpoints planning repas et ingrédients (`/api/v1/meals/*`).
     * `routers/sport.py` : synchronisation d'activités, webhooks et futur dashboard running (`/api/v1/sport/*`).
     * `routers/pwa.py` : routes statiques PWA (`/app`, `/manifest.json`, `/sw.js`).
  2. **Extraction du Dispatcher d'Intentions (`app/core/dispatcher.py`) :**
     * Déplacer la logique métier des branches `case IntentType.*` dans des handlers spécialisés (`meals_handler`, `sport_handler`, `tasks_handler`, etc.) afin que les contrôleurs HTTP restent ultra-légers.
  3. **`app/main.py` épuré (< 80 lignes) :**
     * Rôle unique : assemblage de l'application FastAPI, middlewares (CORS), cycle de vie (`lifespan`) et inclusion des routeurs (`app.include_router(...)`).
  4. **Extraction des factories de connecteurs (suppression de l'import circulaire) :**
     * **Constat :** `get_sport_connector()` / `set_sport_connector()` et `get_meals_connector()` / `set_meals_connector()` (singletons globaux) vivent dans `app/main.py`. Tout router qui en dépend (ex : `routers/sport.py`, introduit à l'Étape 7 du module Sport) doit aujourd'hui les importer en **différé** (`from app import main` à l'intérieur de la dépendance FastAPI) pour éviter le cycle `main → routers.sport → main`.
     * **Correction cible :** déplacer ces factories dans un module dédié (ex : `app/core/dependencies.py`), les exposer comme dépendances FastAPI (`Depends(get_sport_connector)`), et remplacer dans les tests `set_*_connector()` par `app.dependency_overrides`. Conserver temporairement des ré-exports dans `app/main.py` pour la rétrocompatibilité des tests existants, puis les retirer.
     * **Critère de succès :** plus aucun import différé de `app.main` dans `app/routers/`, suite de tests 100 % verte.


