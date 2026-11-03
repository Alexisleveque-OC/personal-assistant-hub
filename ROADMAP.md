# Roadmap - Connecteurs Organisationnels Google Agenda & Google Tasks (Phase 8)

Branche : `feat/calendar-tasks-connectors` (la feature précédente, musique baissée pendant les réponses d'Otis, est dans l'historique git de ce fichier, commit `7094559`)

## Cible
Demander à Otis « qu'est-ce que j'ai aujourd'hui / demain ? », être informé des échéances proches et consulter / ajouter des tâches à la voix, via l'agent Gemini existant (outils typés, comme repas/courses et sport). Gmail perso : feature suivante.

## Décisions (utilisateur, 30/10)
- **Authentification : OAuth utilisateur** (jeton de rafraîchissement), un seul mécanisme pour Agenda, Tasks puis Gmail. Le compte de service reste réservé à Sheets.
  - Tasks n'est pas accessible à un compte de service pour un compte @gmail.com (pas de partage de listes, pas de délégation de domaine).
  - Écran de consentement passé **« In production » sans vérification** (usage personnel, écran « application non vérifiée » accepté une fois) : en statut « Testing », le jeton expire au bout de 7 jours.
  - Scopes : `calendar.readonly` + `tasks` (Gmail ajoutera `gmail.readonly` avec un nouveau consentement).
  - Secret : `.env` en local ; secrets GitHub `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_OAUTH_REFRESH_TOKEN` injectés par la CD comme les autres variables. Jamais commités. Jeton révoqué ou expiré → erreur explicite indiquant de relancer le script de consentement.
  - Pas de `google-api-python-client` : appels REST directs via `google-auth` (déjà présent) + `requests` (déclaré explicitement). `google-auth-oauthlib` sert uniquement au script local de consentement.
- **Agendas lus : tous ceux affichés (cochés) dans Google Agenda** du compte principal, agendas partagés compris (un agenda d'un autre compte se partage au compte principal, aucun second jeton).
- **Réponse orale** : événements « journée entière » d'abord, puis rendez-vous chronologiques (heure, lieu), ~6 maximum puis « et N autres » ; journée vide → « Rien de prévu … ». Horizon court : pas d'interrogation au-delà de 14 jours, échéances proches sur 7 jours par défaut.
- **Échéances** : à la demande en Phase 8 ; résumé proactif dans la Chronique matinale ; notifications push dans une feature dédiée après la Chronique.
- **Tâches** : liste par défaut « Mes tâches » (l'utilisateur). Tâches par personne : voir Hors Périmètre.
- **Cache (règle 8)** : TTL 3 min par période demandée ; invalidation immédiate du cache Tasks à chaque écriture.
- **Données réelles** : lecture réelle de l'agenda autorisée pour la validation ; écritures de tâches de test uniquement dans une liste dédiée « PAH tests », sur accord.

---

## Étapes d'Implémentation (chaque étape : TDD, 100 % vert)

### [x] Étape 1 : Agenda du jour / du lendemain (premier livrable)
- [x] `scripts/google_oauth_login.py` : consentement local (navigateur), affiche le jeton de rafraîchissement sans rien écrire dans le dépôt.
- [x] `app/connectors/google_oauth.py` : identifiants utilisateur depuis les réglages, erreurs explicites (réglage manquant, jeton révoqué).
- [x] `app/connectors/calendar/` : modèles Pydantic (`CalendarEvent`), lecture des agendas cochés, événements récurrents dépliés, fuseau Europe/Paris, cache 3 min.
- [x] Outil agent `get_agenda(date_debut, date_fin)` (14 jours max) + règle de formulation dans le prompt ; erreur explicite si l'agenda n'est pas configuré.
- [x] CD : injection des trois secrets OAuth.
- [x] Validation réelle en lecture (accord utilisateur du 30/10), puis test sur le téléphone (utilisé en prod les 30/10 et 03/11, réponses correctes).

### [ ] Étape 2 : Échéances proches
- [ ] « Qu'est-ce que j'ai cette semaine ? » / « mes prochaines échéances » : agenda sur 7 jours par défaut (+ tâches avec échéance dès l'étape 3).
- Constat prod du 03/11 : « qu'est-ce que j'ai cette semaine ? » est déjà bien traité par `get_agenda` (Gemini choisit seul la période) ; reste à y joindre les tâches à échéance après l'étape 3.

### [x] Étape 3 : Lecture des tâches
- [x] `app/connectors/tasks/` : liste par défaut, tâches non terminées (échéance éventuelle), cache 3 min.
- [x] Outil agent `get_tasks` + règles 15 (lecture à voix haute) et 16 (« cette semaine » = agenda + tâches à échéance) du prompt.
- [x] Intentions regex `LIST_TASKS` / `ADD_TASK` routées vers l'agent : le flux regex n'y répondait que par des phrases fictives codées en dur.
- [x] Test sur le téléphone : « liste-moi mes tâches » OK le 03/11 (4 vraies tâches lues) ; « cette semaine » à confirmer.

### [x] Étape 4 : Ajout et complétion de tâches
- [x] Outils `add_task(titre, echeance?)` et `complete_task(id)`, invalidation du cache ; règles 17-18 du prompt.
- [x] « Annule ça » via le journal d'annulation existant (tâche ajoutée supprimée, tâche cochée rouverte ; refus si elle a changé depuis).
- [x] Décision utilisateur du 03/11 : toute tâche dictée va dans Google Tasks (« rappelle-moi de… », « ajoute une tâche… », « penser à… », « il faut que je… »), avec échéance si elle est dite ; les notes ne gardent que idées, bugs et réflexions. Constat prod : sans `add_task`, l'agent avait rangé « rappelle-moi… » en note « tâche » en répondant « c'est noté dans tes tâches ». `save_note` refuse désormais la catégorie « tâche ».
- [ ] Après déploiement (accord utilisateur du 03/11) : transférer la note « documents pour la PCO » créée par erreur le 03/11 vers Google Tasks, puis la supprimer de la base de prod.
- [x] Factoriser la lecture REST Google (pagination, jeton refusé) dupliquée entre les connecteurs Agenda et Tasks.
- [x] Validation réelle : la liste « PAH tests » est abandonnée (le connecteur n'écrit que dans « Mes tâches ») ; la première écriture réelle est le transfert de la note PCO autorisé le 03/11, puis le test sur le téléphone.

### [x] Étape 4 bis : Onglet Tâches dans la PWA (décision utilisateur du 03/11)
- [x] Onglet « Tâches » sur le modèle de l'onglet Courses : liste des tâches non terminées (échéance, « En retard » en rouge), cocher, ajouter (intitulé + échéance facultative).
- [x] Décisions utilisateur du 03/11 : 6e bouton « Tâches » dans la barre du bas ; cocher écrit tout de suite dans Google Tasks et un toast « Annuler » rouvre la tâche.
- [x] `app/routers/tasks.py` : `GET /api/v1/tasks`, `POST /api/v1/tasks`, `PATCH /api/v1/tasks/{id}` (`terminee`) via `TasksTools` (même validation et mêmes erreurs que l'agent, cache invalidé à chaque écriture) ; 503 si Tasks non configuré, 502 si Google échoue.
- [ ] Test sur le téléphone.

### [ ] Étape 5 (optionnelle) : Voie rapide
- [ ] Phrases exactes « qu'est-ce que j'ai aujourd'hui / demain » sans Gemini, si la latence de l'agent gêne à l'usage.

### [x] Étape 6 : Test d'intégration final & documentation
- [x] Test E2E de bout en bout `tests/test_e2e_calendar_tasks.py` : phrase → agent (LLM scripté) → outils → vrais connecteurs Agenda et Tasks → API Google simulée en mémoire, puis onglet Tâches sur la même liste (cache partagé et invalidé à chaque écriture, cochage puis « Annuler », « annule ça » vocal).
- [x] README : module « Agenda & Tâches », Phase 8 cochée, variables OAuth.
- [ ] Écart de numérotation signalé à l'utilisateur, non corrigé : le README saute la Phase 9 (Chronique matinale = Phase 10 au README, Phase 9 au SPEC ; décalage d'un cran jusqu'à la Domotique) et sa Phase 8 citait Gmail, absent de la Phase 8 du SPEC.

---

## Hors Périmètre
- **Tâches par personne** (« qu'est-ce que <prénom> a à faire aujourd'hui ? », à terme via Alexa) : Google Tasks n'a pas de champ « assigné à » pour un compte perso ; piste : une liste par personne, choisie par l'agent. À cadrer après l'étape 4. Aucun prénom dans le code ni la doc (dépôt public).
- **Notifications push** : feature dédiée après la Chronique matinale.
- **Gmail perso** : feature suivante, nouveau consentement avec `gmail.readonly`.
- Création / modification d'événements d'agenda (lecture seule).
- Secret Manager (`--set-secrets`) à la place des variables d'environnement Cloud Run.
