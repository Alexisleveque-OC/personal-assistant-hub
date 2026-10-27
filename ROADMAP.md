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

### [x] Étape 1 : Outils Métier Typés (indépendants du LLM)
- [x] `app/core/agent/tools/sport_tools.py` : `find_sport_sessions(date_from, date_to, type_seance, statut, limit)`, `get_sport_session(id)`, `update_sport_session(session_id, champs)`, `log_sport_session(...)`, `plan_sport_session(...)`, `undo_sport_mutation(instantané)`.
- [x] Arguments et retours en modèles Pydantic stricts (`sport_models.py`, `extra="forbid"`) ; modifications **par identifiant uniquement**.
  - Création stricte : jamais de fusion avec une séance du même jour, aucune valeur inventée (durée, type).
  - Garde-fous : séance réalisée dans le futur ou planifiée dans le passé refusée (heure de Paris).
- [x] Instantané brut de la ligne avant chaque mutation ; restauration exacte (champs vides compris) ou suppression d'une création.
- [x] Tests unitaires sur SQLite temporaire (`tests/test_agent_sport_tools.py`, 18 tests).

### [ ] Étape 2 : Boucle Agent Gemini (Function Calling)
- [x] `app/core/agent/agent_service.py` : prompt système (`prompt.py`) avec date du jour (Paris), règles « demander plutôt que deviner », 12 séances récentes avec id, historique ; boucle limitée à 4 appels Gemini ; réponse vocale finale.
- [x] Format vérifié dans la documentation officielle : `tools: [{functionDeclarations}]`, parts `functionCall` / `functionResponse` (rôle `user`), tour `model` renvoyé à l'identique (le `thoughtSignature` du premier appel est obligatoire sur Gemini 3, sinon HTTP 400). Schéma des paramètres généré depuis Pydantic (`gemini_schema.py`), registre d'outils (`tool_registry.py`, `tools/sport_registry.py`), client REST (`llm.py`).
- [x] Client Gemini simulé (`tests/agent_fakes.py`, appels scriptés) pour des tests déterministes hors-ligne.
- [x] Erreurs explicites typées (`errors.py`) transportant les mutations déjà effectuées ; erreurs d'outil renvoyées au modèle, jamais masquées ; HTTP 400 → échec immédiat, 429/503 → modèle suivant.
- [x] Essai réel (carnet synthétique, base temporaire) : « c'était du fractionné, RPE 6 » modifie bien la séance du jour par id ; deux séances la veille → question de clarification sans modification.

### [x] Étape 3 : Branchement dans `/interact` (Domaine Sport d'abord)
- [x] Interrupteur `NLU_MODE=legacy|agent` (défaut `legacy`), transmis par la variable GitHub `vars.NLU_MODE` dans `deploy.yml` (`--set-env-vars` écrase tout réglage manuel Cloud Run). Bascule / retour arrière = changer la variable puis redéployer.
- [x] Voie rapide regex conservée (courses, repas, et en attendant l'Étape 5 : listes de notes, apprentissage, annulation legacy). Vont à l'agent : séances sport, planning hebdo, notes, et tout « non compris » (corrections au tour suivant). Garde-fou : « ajoute une séance… » n'est jamais traité comme un article de courses.
- [x] Outil `plan_weekly_training` (`tools/sport_planning.py`) : coach Gemini, création via `plan_sport_session`, jours passés ignorés, jours occupés signalés sans écrasement. Outil `save_note` (`tools/note_tools.py`, anticipé de l'Étape 5 pour ne pas perdre la prise de note du NLU Gemini).
- [x] Les demandes sport passent par l'agent (`handlers/agent_handler.py`) ; panne Gemini → réponse explicite, sans repli regex, avec signalement des modifications déjà appliquées.
- [x] Golden set : nouveau cas « ajoute une séance » (legacy 5/15). **Agent réel : 13/15 (stable sur 2 passages)**, les 2 restants = annulation (Étape 4). Évaluation : `RUN_LIVE_GEMINI=1 .venv/bin/pytest tests/nlu_golden/test_golden_agent_live.py -v -rxX`.

### [x] Étape 4 : Clarification, Annulation Fiable & Mémoire Persistante
- [x] Plusieurs séances candidates → question de clarification. Signal calculé par le code dans le prompt (« jours à plusieurs séances ») : cas réel passé de 0/5 à 5/5 ; identifiants techniques jamais prononcés.
- [x] « Annule ce que tu viens de faire » → restauration exacte depuis l'instantané (`app/core/agent/undo.py`) :
  - « annule ça » seul : annulation déterministe, sans appel Gemini ; phrase composée : outil agent `undo_last_action`.
  - Tout ou rien, ordre inverse ; refus explicite si la séance a été modifiée depuis (éditeur, import) ; notes de l'agent annulables.
  - Si la dernière action vient du flux regex (ex. ajout aux courses), c'est l'annulation legacy qui s'applique.
- [x] Instantanés persistés en SQLite (table `agent_undo_batches`, un lot par tour et par session) : l'annulation survit aux redémarrages Cloud Run. L'historique de conversation était déjà rechargé depuis `conversation_logs` par `SessionManager` (constat initial erroné sur ce point).
- [x] Golden set agent réel : **15/15**.

### [x] Étape 5 : Extension aux Autres Domaines & Allègement des Regex
- [x] Outils courses (`tools/meals_tools.py`) : lire, ajouter avec rayon (rayon inconnu → choisi par l'agent parmi les rayons du classeur), cocher/décocher, retirer, vider les articles cochés. Outils repas : planning (14 jours max), modifier un repas, lire une recette. Écritures via le connecteur (cache invalidé), annulation exacte par le journal, y compris les mutations enchaînées sur un même article.
- [x] Voie rapide regex (`handlers/fast_lane.py`) limitée aux demandes non ambiguës : « ajoute X », lecture de la liste, « qu'est-ce qu'on mange », vider (dont les 3 phrases envoyées par la PWA). Phrases composées, nuancées ou d'un autre domaine → agent (ex. « ajoute des lasagnes au menu de demain soir » était lu comme une consultation).
- [x] Garde-fous déterministes (le prompt seul était instable sur plusieurs passages) : plat hors carnet confirmable seulement au tour suivant ; jour à plusieurs séances → modification refusée si le type n'est pas nommé dans les mots de l'utilisateur (`tools/session_types.py`).
- [x] Réponse courte (« d'accord ») à une question de l'agent → renvoyée à l'agent. Notes toujours en français (règle de prompt + contrôle dans le golden set) ; vérification réelle dédiée à refaire (quota Gemini épuisé le jour même).
- [x] Golden set : 29 cas (14 courses/repas). Legacy 12/29, **agent réel 28-29/29** sur 4 passages (échecs résiduels corrigés au fil des passages).
- [ ] Retrait des branches regex redondantes en mode agent (sport 9.1 bis-9.4, `SAVE_NOTE`, recettes, planification repas, coche courses) : **reporté après le déploiement** et une période d'observation, car elles assurent le retour arrière `NLU_MODE=legacy`.
- [x] Rayon d'un article inconnu : voir Étape 5 bis (remplace le choix du rayon par l'agent, gardé en mémoire seulement).

### [ ] Étape 5 bis : Rayon Demandé à l'Utilisateur & Enregistré dans le Classeur
- [x] Logique unique (`app/core/shopping/rayon_questions.py`) pour la voie rapide « ajoute X » et l'outil agent `add_shopping_items` : un article inconnu n'est pas ajouté ; l'application demande son rayon en proposant 2 rayons de l'onglet « Rayons » (`app/core/llm/rayon_suggester.py`, 1 appel Gemini par nouvel article, sans « Divers » ; question ouverte si Gemini est indisponible). Plusieurs articles inconnus : une question à la fois.
- [x] Réponse traitée par le code au tour suivant, sans LLM (`handlers/rayon_question_handler.py`, avant tout aiguillage dans `/interact`) :
  - rayon de l'onglet (« en entretien », « le premier », « divers ») → ligne ajoutée en fin de `Ingredients_Rayons`, cache des rayons invalidé, article ajouté : la question n'est posée qu'une fois ;
  - « non », « annule », « laisse tomber » → rien n'est ajouté ni enregistré ;
  - autre chose → article ajouté et enregistré avec un rayon vide (« son rayon sera à trier plus tard dans votre sheet »), affiché en Divers ; une vraie demande est ensuite traitée normalement.
- [x] Rayon dicté par l'utilisateur (« au rayon hygiène ») : enregistré directement. Garde-fou : le rayon passé par l'agent n'est retenu que s'il figure dans les mots de l'utilisateur.
- [x] « Annule ça » : annulation exacte par le journal en mode agent (article retiré + ligne `Ingredients_Rayons` supprimée) ; en mode legacy, l'article seul est retiré.
- [x] Cache des rayons : TTL de 3 min (auparavant jamais rafraîchi avant redémarrage), pour prendre en compte un tri manuel dans le classeur.
- [x] Retirés car remplacés : `infer_rayon_with_llm` (ajout sans demander), `suggest_rayons_for_item` (rayons en dur), branches `clarify_shopping_rayon`.
- [x] Golden set : 4 cas (question, réponse enregistrée, annulation, via l'agent) + attente `rayons_appris`. Legacy 16/33.
- [x] Validation réelle (27/10) : golden agent **33/33** sur `gemini-3.5-flash-lite` (69 appels), notes rédigées en français. Prompt (règle 10) renforcé : l'agent ne mentionne plus l'article au rayon inconnu, la question de l'application suit (doublon constaté puis corrigé, 3/3 en réel).
- [x] Tests réels figés sur `gemini-3.5-flash-lite` (500 req/j, 15 req/min), compteur d'appels et espacement par minute.
- [x] Sport (vision capture, plan coach, conseil Otis) : meilleurs modèles d'abord (3.8 → 3.6 → 3.5 Lite), relais au modèle inférieur sur quota, sans promouvoir 3.8 pour le reste de l'application (`premium_candidate_models`).

### [ ] Étape 6 : Validation Réelle & E2E
- [x] Évaluation du golden set contre le vrai Gemini (`RUN_LIVE_GEMINI=1`, hors CI) : 33/33 le 27/10.
- [x] Test d'intégration E2E du flux complet (phrase → outils → base → réponse) : `tests/test_e2e_agent_flow.py` (sport par identifiant, courses + question de rayon, note sur l'échange précédent, annulation). Bug trouvé et corrigé : « ajoute X aux courses » gardait « aux courses » dans le nom de l'article.
- [x] Notes sur les échanges précédents : résumé précis + extrait exact du dernier échange ajouté par le code (`inclure_dernier_echange`), 3/3 en réel.
- [x] Mesure de latence (27/10, vrai Gemini 3.5 Flash Lite, 2 passes de 9 phrases) : voie rapide et réponses traitées par le code < 0,1 s ; tour agent = 2 appels Gemini successifs (outil puis réponse), médiane 8 s, de 2,7 à 16,5 s ; appel Gemini de 0,6 à 9 s selon la charge de Google ; code + outils ≈ 0,2 s (hors latence Google Sheets en prod). Les 20-70 s observés en test venaient du dépassement de 15 req/min (429 → pause du modèle et relais), pas du code.
- [x] Mise à jour du `README.md` (fin de phase), suite `pytest` 100 % verte.

### [x] Étape 7 : Latence Ressentie (décisions du 27/10/2026)
- [x] Réponse directe après une modification simple (`app/core/agent/fast_reply.py`) : séance modifiée, enregistrée ou planifiée ; articles ajoutés, cochés ou retirés ; note enregistrée → l'application rédige la confirmation, pas de 2e appel Gemini. Gemini garde la main pour les lectures, le plan de la semaine, les repas, les erreurs, les rayons à demander et les demandes composées (« et », « puis », « aussi », « ensuite »).
- [x] Journalisation de la latence par tour : `conversation_logs.parameters` contient `llm_calls` (modèle, durée de chaque appel Gemini) et `fast_reply`, y compris en cas d'échec.
- [x] PWA : bulle animée « Otis réfléchit… » pendant l'attente (texte et vocal), retirée à la réponse ou en cas d'erreur ; cache Service Worker v22.
- [x] Validation réelle : golden agent 33/33 en 53 appels (69 avant). Mesure : modification simple en 1 appel Gemini (≈ 1 s quand Gemini est rapide, contre 2 appels avant).

---

## Hors Périmètre (à traiter ensuite)
- **Musique baissée pendant l'écoute du mot-clé « Otis » (Android)** : l'écoute continue via Web Speech API prend le focus audio ; `navigator.audioSession` est sans effet sur Chrome Android. Piste : détection locale du mot-clé via `getUserMedia` sans traitements audio, à valider d'abord sur l'appareil.
