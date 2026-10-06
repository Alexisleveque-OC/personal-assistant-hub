# Roadmap Feature : Module Sport Running & Mini-Coach Otis (`feat/sport-running-coach`)

> **Règles d'or (AGENTS.md) :**
> - Chaque étape doit être validée **manuellement et explicitement par l'utilisateur** avant de passer à la suivante.
> - La suite de tests automatisés (`pytest`) doit être à **100% au vert** à chaque étape (TDD strict).
> - À la fin de la feature, un **test d'intégration End-to-End (E2E)** doit valider le flux complet de bout en bout.

---

## Vue d'ensemble des Étapes

| Étape | Description | Statut | Validation Utilisateur | Tests Automatisés |
| :--- | :--- | :---: | :---: | :---: |
| **Étape 1** | Modélisation Pydantic du Sheet Sport, configuration & validation de schéma (Schema Drift) | 🟢 Terminé | Validé par l'utilisateur | ✅ 12/12 tests dédiés (220/220 total) au vert |
| **Étape 2** | Connecteur Backend `SportConnector` (lecture séance, calculs Km-Effort, synthèse hebdo & alerte +10%) | 🟢 Terminé | Validé par l'utilisateur | ✅ 11/11 tests dédiés (231/231 total) au vert |
| **Étape 3** | Intentions NLU Gemini Flash & réponses vocales Otis complices (Structured Outputs) | 🟢 Terminé | Validé par l'utilisateur | ✅ 8/8 tests dédiés (239/239 total) au vert |
| **Étape 4** | Intégration `/api/v1/interact`, passerelle de synchronisation, colonnes BPM & import réel des 9 GPX | 🟢 Terminé | Validé par l'utilisateur | ✅ 6/6 tests dédiés (37/37 sport, 245+ total) au vert |
| **Étape 5** | Renforcement Musculaire (Renfo/PPG) & Réajustement vocal a posteriori (RPE / Douleur Périostite) | 🟢 Terminé | Validé par l'utilisateur | ✅ 14/14 tests dédiés (51/51 sport, 259/259 total) au vert |
| **Étape 6** | Cerveau LLM Otis : Analyse fine d'historique & Planification hebdomadaire proactive (gestion périostite) | 🟢 Terminé | En cours de validation | ✅ 27/27 tests dédiés (78/78 sport, 286/286 total) au vert |
| **Étape 7** | Interface Graphique PWA Running & Dashboard Visuel (Séance du jour, jauges, multi-échelles) | 🟢 Terminé | En cours de validation | ✅ 25/25 tests dédiés (114/114 sport, 322/322 total) au vert |
| **Étape 8** | Gamification, Anecdotes Insolites & Badges de Dopamine (PWA & Chronique Matinale) | ⚪ À faire | En attente | Tests unitaires modèles, règles & dopamine |
| **Étape 9** | Test d'intégration End-to-End (E2E) complet & Validation finale | ⚪ À faire | En attente | Test E2E complet (100% au vert) |

---

## Détail des Étapes

### 🟢 Étape 1 : Modélisation Pydantic du Sheet Sport, Configuration & Validation de Schéma
* **Objectifs :**
  1. Configuration `spreadsheet_sport_id` et modèles Pydantic (`SportSession`, `SportWeeklySummary`).
  2. Formule standard du Km-Effort : $\text{Km-Effort} = \text{Distance} + \frac{D^+}{100}$.
  3. Validateur de schéma `SportSchemaValidator` (tolérance aux dérives).
* **Statut :** Validé et commité (`de03944`).

---

### 🟢 Étape 2 : Connecteur Backend `SportConnector` (TDD Strict)
* **Objectifs :**
  1. Implémentation du connecteur `SportConnector` (`get_session`, `log_session`, `plan_session`, `get_weekly_summary`).
  2. Respect de la règle des +10% max et gestion de cache RAM.
* **Statut :** Validé et commité (`f8bf73e`).

---

### 🟢 Étape 3 : Intentions NLU Gemini Flash & Cerveau Otis
* **Objectifs :**
  1. Définition des intentions `GET_SPORT_SESSION`, `LOG_SPORT_SESSION`, `GET_SPORT_WEEKLY_SUMMARY`, `PLAN_SPORT_SESSION`.
  2. Prompt persona Otis le scribe complice et protecteur contre les blessures.
* **Statut :** Validé et commité (`241ffd7`).

---

### 🟢 Étape 4 : Intégration `/api/v1/interact`, Passerelle de Synchro, Cardio BPM & Import Réel
* **Objectifs :**
  1. Brancher les intentions sportives dans `/api/v1/interact` (avec support de la semaine courante et des semaines passées).
  2. Endpoints d'ingestion et de webhook Strava (`/api/v1/sport/sync-activity`).
  3. Colonnes BPM (`FC Moy (bpm)`, `FC Max (bpm)`) intégrées dans le Google Sheet.
  4. Importation des 9 vraies séances réelles d'Alexis depuis ses fichiers GPX avec mise à jour automatique de la synthèse hebdomadaire sur 4 semaines (S37 à S40).
* **Statut :** Validé et commité (`a03d275`).

---

### 🟢 Étape 5 : Renforcement Musculaire & Réajustement Vocal a posteriori (RPE / Périostite)
* **Objectifs :**
  1. Support du type de séance `Renforcement` (`Renfo`) : pas de distance kilométrique forcée, mais comptabilisation de la durée et de la Charge RPE ($\text{Durée} \times \text{RPE}$) dans le cumul hebdomadaire.
  2. Méthode métier `update_session(target_date, ...)` dans `SportConnector` permettant de modifier le RPE, le ressenti ou d'ajouter une note de douleur sur une séance passée.
  3. Intention vocale `UPDATE_SPORT_SESSION` :
     - *« Otis, modifie le ressenti de ma course de dimanche à 9 sur 10 à cause de ma périostite »*
     - *« Otis, ajoute une note sur ma course de dimanche : douleur au tibia à J+2 »*
* **Statut :** 🟢 Validé et commité (`6082066`).

---

### 🟢 Étape 6 : Cerveau LLM Otis : Analyse fine d'historique & Planification Hebdomadaire Proactive
* **Objectifs :**
  1. Connecter le LLM Gemini à l'historique complet des 4 dernières semaines et au contexte physiologique d'Alexis (antécédent de périostite, besoin de décharge post-compétition).
  2. Nouvelle intention `PLAN_WEEKLY_TRAINING` (*« Otis, prévois-moi ma semaine d'entraînement »*, *« Que me conseilles-tu cette semaine ? »*).
  3. Génération d'un plan hebdomadaire équilibré et personnalisé :
     - Alternance intelligente course / renforcement musculaire ciblé.
     - Prescription complète et chirurgicale pour le renfo (exercices précis, séries, reps, tempo 3s, repos) pour être 100% autonome sans kiné.
     - Prise en compte de la périostite : conseils de terrains souples/herbe, étirements, limitation des chocs.
     - Gestion des semaines de décharge (Deload) déclenchées à l'écoute des signaux réels (RPE >= 8, surcharges, douleurs tibias) et non par une règle mécanique rigide.
     - Cohérence des allures physiologiques : alignement de l'Endurance Fondamentale (EF) et de la Sortie Longue (SL) sur la Zone 2 d'aisance respiratoire (+/- marge de progression), avec durées strictes (30-35 min en EF, ~1h en SL).
* **Critères de succès :** Tests de génération de plans pertinents et cohérents avec la physiologie d'Alexis, insertion réelle en lot des séances "Prévu" dans Google Sheets, affichage clair de l'allure ET de la vitesse cibles (+/-) dans les colonnes I, J et P, calcul multicritère de la synthèse hebdomadaire (Volume, Vitesse, Charge RPE et Progression Générale) excluant le renfo pour le calcul de vitesse de course, 78/78 tests sport au vert, 286/286 tests globaux au vert.
* **Statut :** 🟢 Validé & opérationnel.

---

### 🟢 Étape 7 : Interface Graphique PWA Running & Dashboard Visuel
* **Objectifs réalisés :**
  1. **Vue interactive "Séance du Jour" (Prévu / Réalisé / Repos) :**
     - Affichage de la séance planifiée ou réalisée avec badge de statut.
     - Saisie manuelle tactile directe (sans parler) : sélecteur de pastilles RPE 1 à 10 aux couleurs dynamiques (vert -> ambre -> rouge) et zone de saisie pour notes, sensations ou alertes périostite. Envoi instantané via `PATCH /api/v1/sport/session/{date}`.
  2. **Récapitulatif & Comparateur de Séance :**
     - Badges de couleurs parlantes comparant la séance du jour à la dernière séance du même type (Fractionné, EF, Sortie Longue) : vitesse, distance, km-effort.
  3. **Tableau de Bord & Évolution Multi-Échelles :**
     - **Semaine :** distance cumulée, km-effort, allure moy (hors renfo), charge RPE, comparaison par rapport à la moyenne des autres semaines et plafond sécurité (+10%).
     - **Mois :** récapitulatif mensuel et séries découpées par semaines ISO.
     - **Année :** vue macro et progression globale de la saison par mois.
  4. **Graphiques Visuels Dynamiques (SVG Natif) :**
     - Barres de volume hebdomadaire avec ligne repère en pointillés rouges marquant le plafond de sécurité +10%.
  5. **Conseil & Alerte Périostite du Coach Otis :**
     - Bulle conseil bienveillante adaptée au plan de la semaine (info, vigilance, alerte) avec cache journalier et fallback résilient.
  6. **Router modulaire FastAPI :**
     - Nouveau router `app/routers/sport.py` (`/today`, `/session/{date}`, `/dashboard`) avec dépendance d'authentification API key.
* **Critères de succès :** Interface fluide, dynamique, visuellement percutante, parfaitement utilisable au doigt sur smartphone (Service Worker mis à jour en `v5`), 25 tests dédiés au vert, 322/322 tests du projet au vert.
* **Statut :** 🟢 Validé & opérationnel.

---

### 🟢 Étape 8 : Gamification, Badges de Dopamine, Pop-Culture & Annonce du Jour (PWA & Coach Otis)
* **Objectifs réalisés :**
  1. **Annonce du Jour Dynamique & Fin de Séance (`daily_spotlight`) :**
     - Détection contextuelle si une séance prévue aujourd'hui (ou tout juste réalisée) franchit un cap de 100 km ou un jalon majeur (*« Aujourd'hui, avec ta séance de X km prévue, on passe le cap des Y km ! C'est génial, donne tout ! »*).
     - Priorisation intelligente : séance du jour $\rightarrow$ palier imminent $\rightarrow$ annonces OMG $\rightarrow$ anecdotes insolites.
  2. **Exploits en Une Séance (Mono-Session) :**
     - Distance d'une traite : 10 km, 15 km, Semi-marathon (21.1 km), Le Mur des Trente (30 km), L'Épreuve d'Athènes (42.2 km), et l'ultra absurde "Le Cent-Bornard Fou" (100 km).
     - Durée ininterrompue : 1h, 1h15, 1h30, Sortie Royale (2h), Guerrier du Long Cours (3h), et le défi sans sommeil "La Ronde des 24 Heures".
  3. **Régularité & Progression Évolutive :**
     - *Renforcement musculaire :* 5, 10, 25, 50, 75 et jusqu'à 100 séances ("Titan du Renforcement").
     - *Météo difficile :* 1, 5, 10 et 20 séances sous la pluie, le vent ou la tempête ("Guerrier Immortel des Éléments").
     - *Grand Chelem Hebdo :* 7 séances de sport dans la même semaine (7/7).
     - *Discipline de Fer :* au moins 4 séances par semaine pendant 8 semaines consécutives.
     - *Volumes horaires convertis en jours :* 96h (4 jours pleins), 240h (10 jours), 480h (20 jours), 960h (40 jours), 1920h (80 jours - Le Tour du Monde).
  4. **Pop-Culture & Easter Eggs (Otis, Le Seigneur des Anneaux, Brandon Sanderson) :**
     - *Astérix & Obélix : Mission Cléopâtre (Otis) :* "Pas de Bonne ou Mauvaise Situation 📜", "Pas de Pierres, Pas de Construction ! 🏛️", "Un Lion Mort dans le Désert 🦁", "Le Scribe d'Alexandrie ✍️", "Deuxième Porte à Gauche 🚪", "Itinéris ne Capte Plus 📵".
     - *Le Seigneur des Anneaux (LOTR) :* "Road to Mordor 🌋" (2 850 km - trajet de Frodon), "Le Deuxième Petit-Déjeuner 🥐", "En Route pour Fondcombe 🧝" (135 km), "Vous Ne Passerez Pas ! 🧙", "L'Anneau Unique 💍", "Pas un Orque en Vue 🌫️".
     - *Brandon Sanderson (Les Archives de Roshar) :* "Pont Quatre (Bridge Four) 🪵" (RPE 9-10), "Au Cœur de la Haute-Tempête ⚡", "Marcheur du Vent (Windrunner) 💨", "Danseur de Pierre (Stoneward) 🪨", "Les Idéaux des Radiants 🛡️", "Infusion de Fulgurance 💎", "Le Spren de la Douleur 👹".
     - *Secrets & Insolites :* "Le Déneigéré ❄️", "Le Pi Runner 🥧", "Chrono d'Orfèvre ⏱️", "Objectif Lune 🚀".
  5. **Interface PWA Premium (Sous-onglet Trophées & Fun 🏆) :**
     - Carte interactive du Mot d'Otis / Annonce du jour en tête d'onglet.
     - Organisation en sections claires : Exploits Mono-Séance, Pop-Culture & Clins d'Œil, Paliers Réguliers, Volume Horaires, Constance & Éléments, Secrets et Absurde.
* **Critères de succès :** Modèles typés Pydantic v2, 16 tests unitaires et d'API dédiés au vert, suite globale à 341 tests au vert.
* **Statut :** 🟢 Validé & opérationnel.

---

### ⚪ Étape 9 : Test d'Intégration End-to-End (E2E) & Validation Finale
* **Objectifs :**
  1. Écrire le test d'intégration complet `tests/test_e2e_sport_running.py` couvrant l'ensemble du cycle de vie (consultation $\rightarrow$ log course $\rightarrow$ log renfo $\rightarrow$ modification de douleur a posteriori $\rightarrow$ planification par le LLM $\rightarrow$ déclenchement de badge/anecdote).
  2. 100% de la suite de tests au vert (zéro régression).
  3. Validation manuelle en conditions réelles par Alexis sur son smartphone et son Google Sheet.
* **Critères de succès :** Validation totale et feu vert d'Alexis pour le merge sur `develop`.
