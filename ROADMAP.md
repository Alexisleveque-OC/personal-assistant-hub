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

### [ ] Étape 1 : Agenda du jour / du lendemain (premier livrable)
- [ ] `scripts/google_oauth_login.py` : consentement local (navigateur), affiche le jeton de rafraîchissement sans rien écrire dans le dépôt.
- [ ] `app/connectors/google_oauth.py` : identifiants utilisateur depuis les réglages, erreurs explicites (réglage manquant, jeton révoqué).
- [ ] `app/connectors/calendar/` : modèles Pydantic (`CalendarEvent`), lecture des agendas cochés, événements récurrents dépliés, fuseau Europe/Paris, cache 3 min.
- [ ] Outil agent `get_agenda(date_debut, date_fin)` (14 jours max) + règle de formulation dans le prompt ; erreur explicite si l'agenda n'est pas configuré.
- [ ] CD : injection des trois secrets OAuth.
- [ ] Validation réelle en lecture (accord utilisateur du 30/10), puis test sur le téléphone.

### [ ] Étape 2 : Échéances proches
- [ ] « Qu'est-ce que j'ai cette semaine ? » / « mes prochaines échéances » : agenda sur 7 jours par défaut (+ tâches avec échéance dès l'étape 3).

### [ ] Étape 3 : Lecture des tâches
- [ ] `app/connectors/tasks/` : liste par défaut, tâches non terminées (échéance éventuelle), cache 3 min.
- [ ] Outil agent `get_tasks`.

### [ ] Étape 4 : Ajout et complétion de tâches
- [ ] Outils `add_task(titre, echeance?)` et `complete_task(id)`, invalidation du cache.
- [ ] « Annule ça » via le journal d'annulation existant.
- [ ] Validation réelle dans la liste « PAH tests » uniquement.

### [ ] Étape 5 (optionnelle) : Voie rapide
- [ ] Phrases exactes « qu'est-ce que j'ai aujourd'hui / demain » sans Gemini, si la latence de l'agent gêne à l'usage.

### [ ] Étape 6 : Test d'intégration final & documentation
- [ ] Test E2E de bout en bout (requête → agent → connecteurs simulés → réponse).
- [ ] README (signaler l'écart de numérotation des phases SPEC/README avant toute correction).

---

## Hors Périmètre
- **Tâches par personne** (« qu'est-ce que <prénom> a à faire aujourd'hui ? », à terme via Alexa) : Google Tasks n'a pas de champ « assigné à » pour un compte perso ; piste : une liste par personne, choisie par l'agent. À cadrer après l'étape 4. Aucun prénom dans le code ni la doc (dépôt public).
- **Notifications push** : feature dédiée après la Chronique matinale.
- **Gmail perso** : feature suivante, nouveau consentement avec `gmail.readonly`.
- Création / modification d'événements d'agenda (lecture seule).
- Secret Manager (`--set-secrets`) à la place des variables d'environnement Cloud Run.
