# Roadmap - Phase 6.8 : Cerveau LLM-First (Compréhension Intelligente des Demandes)

Branche : `feat/llm-first-nlu`

## Constat (logs de production, 46 échanges du 10 au 22/10/2026)
- **Le LLM n'intervient qu'en dernier recours** : `interact.py` exécute d'abord `IntentParser.parse()` (~1 000 lignes de regex) et n'appelle Gemini que si le résultat est `UNKNOWN`. 36 échanges sur 46 n'ont jamais atteint le LLM.
- **Mauvaise séance ciblée** : « modifie le RPE de ma dernière séance de renfo » → sortie longue du jour modifiée ; « c'était une séance de fractionné, RPE à 3 » → séance du 28/09 modifiée ; « RPE 4 car courbatures suite à la séance de renfo » → renfo du 06/10 modifié au lieu de la séance du jour ; « j'ai fait une séance de fractionné » → réponse « renforcement enregistré ».
- **Commandes méta incomprises** : « annule ce que tu viens de faire », « prends note de ces 3 derniers échanges ».
- **Ciblage par date, jamais par identifiant** : `sport_handler.py` déduit une date via plusieurs heuristiques (`last`, `last_sport_date`, jour de la semaine) puis modifie « la séance de cette date ».
- **Le LLM ne voit pas les données** : il ne peut pas résoudre « la dernière séance de renfo » sans connaître les séances existantes.
- **Contexte volatil** : l'historique de session (`SessionManager`) est en RAM → perdu à chaque redémarrage d'instance Cloud Run.
- **Fuseau horaire** : aucun `TZ` dans le conteneur (UTC) → entre 00h et 02h (Paris), « aujourd'hui » = la veille côté serveur.

## Cible
Gemini en premier, avec **appel de fonctions typées** (function calling) : le modèle cherche les séances, choisit celle qui correspond (par **identifiant**), puis la modifie. Il demande une précision quand plusieurs séances correspondent au lieu de deviner. Les regex ne restent qu'en voie rapide pour quelques commandes sans ambiguïté.

Compromis assumé : ~1 à 2 s par requête au lieu de quelques ms, 1 à 3 appels Gemini par requête (quota `GEMINI_MAX_DAILY_REQUESTS` = 1000/jour à surveiller).

---

## Étapes d'Implémentation (chaque étape : TDD, 100 % vert, validation utilisateur)

### [x] Étape 0 : Jeu de Référence (Golden Set) & Fuseau Horaire
- [x] Construire `tests/nlu_golden/` : cas **réécrits et anonymisés** (le dépôt est public : aucun prénom, aucune donnée de santé réelle) reproduisant la structure des échecs de prod. Chaque cas = état initial du carnet + phrase (+ historique) → effet attendu (séance ciblée par id, champs modifiés, ou question de clarification).
- [x] Mesurer le score du parser actuel sur ce jeu (cas en échec marqués `xfail` comme cibles).
  - **Score legacy (regex + handlers, Gemini désactivé) : 5/14 cas.** Échecs : précision au tour suivant, ciblage par type de séance, mention d'un autre type, planification (« sortie longue » enregistrée en EF), annulation, phrase composée annule + note, note sur l'historique, clarification, séance inexistante « mise à jour ».
  - Constat annexe : « j'ai fait une séance de fractionné » enregistre une durée de 30 min jamais dite.
- [x] Fuseau horaire `Europe/Paris` : helper unique `app/core/clock.py` (`paris_today()`, `paris_now()`) pour le nouveau NLU, et `TZ=Europe/Paris` dans le conteneur (corrige aussi les `date.today()` existants en prod).
  - Le harnais golden utilise encore `date.today()` (même horloge que le code legacy) : à basculer sur `paris_today()` quand l'agent sera branché.

### [ ] Étape 1 : Outils Métier Typés (indépendants du LLM)
- [x] `app/core/agent/tools/sport_tools.py` : `find_sport_sessions(date_from, date_to, type_seance, statut, limit)`, `get_sport_session(id)`, `update_sport_session(session_id, champs)`, `log_sport_session(...)`, `plan_sport_session(...)`, `undo_sport_mutation(instantané)`.
- [x] Arguments et retours en modèles Pydantic stricts (`sport_models.py`, `extra="forbid"`) ; modifications **par identifiant uniquement**.
  - Création stricte : jamais de fusion avec une séance du même jour, aucune valeur inventée (durée, type).
  - Garde-fous : séance réalisée dans le futur ou planifiée dans le passé refusée (heure de Paris).
- [x] Instantané brut de la ligne avant chaque mutation ; restauration exacte (champs vides compris) ou suppression d'une création.
- [x] Tests unitaires sur SQLite temporaire (`tests/test_agent_sport_tools.py`, 18 tests).

### [ ] Étape 2 : Boucle Agent Gemini (Function Calling)
- [ ] `app/core/agent/agent_service.py` : prompt système avec date du jour (Paris), résumé des séances récentes, historique ; boucle outils limitée (ex. 4 tours max) ; réponse vocale finale.
- [ ] Vérifier le format exact de l'API Gemini (`tools.functionDeclarations`, parts `functionCall` / `functionResponse`) dans la documentation officielle avant d'implémenter.
- [ ] Client Gemini simulé (appels de fonctions scriptés) pour des tests déterministes hors-ligne.
- [ ] Erreurs explicites : panne Gemini → message clair, jamais de repli silencieux qui modifie des données.

### [ ] Étape 3 : Branchement dans `/interact` (Domaine Sport d'abord)
- [ ] Interrupteur de configuration `NLU_MODE=agent|legacy` (bascule et retour arrière immédiats).
- [ ] Voie rapide regex conservée uniquement pour : « ajoute X », « liste de courses », « qu'est-ce qu'on mange ».
- [ ] Outil `plan_weekly_training` pour l'agent (sinon régression du planning hebdo) : réutilise `SportCoachService`, crée via `plan_sport_session` (jamais d'écrasement), ignore les jours passés, signale les jours déjà occupés au lieu de les écraser.
- [ ] Les demandes sport passent par l'agent ; le golden set sport passe au vert.

### [ ] Étape 4 : Clarification, Annulation Fiable & Mémoire Persistante
- [ ] Plusieurs séances candidates → question de clarification (« Tu parles du renfo du 06/10 ou du fractionné d'aujourd'hui ? »).
- [ ] « Annule ce que tu viens de faire » → restauration exacte depuis l'instantané.
- [ ] Historique de conversation et instantanés persistés en SQLite (survivent aux redémarrages Cloud Run).

### [ ] Étape 5 : Extension aux Autres Domaines & Allègement des Regex
- [ ] Outils courses, repas, second cerveau ; prise de note sur référence (« note ces derniers échanges »).
- [ ] Notes enregistrées en français (des notes ont été stockées en anglais en prod).
- [ ] Retrait progressif des branches regex devenues inutiles dans `intent_parser.py`.

### [ ] Étape 6 : Validation Réelle & E2E
- [ ] Évaluation optionnelle du golden set contre le vrai Gemini (test marqué `live`, hors CI).
- [ ] Test d'intégration E2E du flux complet (phrase → outils → base → réponse).
- [ ] Mise à jour du `README.md` (fin de phase), suite `pytest -v` 100 % verte.

---

## Hors Périmètre (à traiter ensuite)
- **Musique baissée pendant l'écoute du mot-clé « Otis » (Android)** : l'écoute continue via Web Speech API prend le focus audio ; `navigator.audioSession` est sans effet sur Chrome Android. Piste : détection locale du mot-clé via `getUserMedia` sans traitements audio, à valider d'abord sur l'appareil.
