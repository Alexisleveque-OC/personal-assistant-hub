# Roadmap - Phase 10 : connecteur Budget (Google Sheets)

Branche : `feat/budget-connector` (depuis `develop`). La roadmap précédente (Phase 6.10, cerveau en cascade) est dans l'historique git de ce fichier (commit `32931ab`).

## Objectif
Interroger et alimenter à la voix le classeur budget existant (`SPREADSHEET_BUDGET_ID`), **sans casser** le flux actuel de l'utilisateur : copier-coller bancaire → menu Apps Script « Budget » (import, détection des doublons validée à la main, tri auto, échéanciers, dépenses multiples).

## Le classeur (lu le 23/11)
- Saisies : `Débit` et `Swile` (Date | Montant | Type = catégorie | Commentaires | Intitulé), `Revenus` (Date | Montant | Type | Commentaires | Intitulé), `Autre`.
- `Catégories` (Catégorie | Date de création | Date de fin) ; `Tri auto` (mot-clé du libellé bancaire → catégorie).
- `Gestion` : une ligne par catégorie (groupes Courants, Vêtement, Cadeaux, Loisir, Fixes, Divers, A rembourser, Epargne, Revenus) ; colonne B = **reste total** ; un bloc de 3 colonnes par mois (Prévu | Équilibrage | **Reste fin du mois**), mois en ligne 2.
- Mois actif = dernière case cochée en ligne 4 de `Total dépenses` (même règle que l'Apps Script `getActiveMonth`).
- `Échéanciers` (Nom | Montant total | Nb échéances | Échéance actuelle | Mensualité | Mois début « novembre 2026 » | Catégorie | Commentaires | Statut Actif/Terminé).
- `Dépenses Multiples` (Date approximative | Mot-clé banque | Montant total | Statut « A traiter »/« Traité » | Description | Parts en JSON `[{"category","amount"}]`).
- L'import consomme ces deux onglets (rapprochement d'une échéance ou d'un découpage, compteur, statut) : Otis écrit **le même format** que les formulaires de l'Apps Script, sans passer par le menu.
- Doublons à l'import : même montant à ±2 jours (catégories différentes = pas doublon) → l'utilisateur valide.

## Décisions utilisateur (23/11)
- Lecture :
  - « combien il reste en Course ? » → **reste total** (colonne B de `Gestion`) ; « … ce mois-ci ? » → reste fin du mois du mois actif.
  - « combien j'ai touché en CAF ce mois-ci / le mois dernier ? » → somme de `Revenus` par type et par mois.
  - Échéanciers : liste des actifs **et** suivi d'un échéancier précis.
- Écriture (sans confirmation : Otis relit ce qu'il a écrit, et « Annuler » permet de corriger) :
  - dépense → `Débit` (ou `Swile` si « en Swile / ticket resto ») ; revenu → `Revenus` ; intitulé `Otis : <libellé dicté>` (reconnaissable dans la fenêtre de doublon de l'import) ;
  - échéancier → `Échéanciers` ; dépense multiple pré-déclarée (« dépense d'avance ») → `Dépenses Multiples`.
- Catégorie toujours donnée par l'utilisateur : rapprochement avec `Catégories` (sans accents ni casse), puis avec les mots-clés de `Tri auto`, sinon **question**. Jamais d'invention.
  - Un seul nom proche (« cadeau candice » → « Cadeaux Candice ») est retenu sans question ; l'utilisateur corrige au besoin (« non, c'était dans la catégorie X »). Plusieurs choix possibles → question.
  - Nom de groupe (Loisir, Courants…) : en lecture, reste du groupe = somme de ses catégories (comme sa ligne « Total ») ; en écriture, question « laquelle ? » avec la liste des catégories du groupe. Catégorie homonyme de son groupe (« Epargne ») : la catégorie l'emporte.
- Écriture, précisions du 23/11 (après l'étape 2) :
  - date = aujourd'hui sauf date dite (« hier ») ; intitulé `Otis : <libellé dicté>` en colonne E (Débit, Revenus) ; commentaire vide ;
  - « non, c'était dans la catégorie X » → Otis **modifie la catégorie (colonne Type)** de la ligne qu'il vient d'écrire, seulement si elle est restée identique (sinon refus « modifiée depuis ») ;
  - remboursement (« je me suis fait rembourser 20 € en Santé ») → ligne **négative dans `Débit`** dans la catégorie ;
  - revenu → catégories du **groupe Revenus** de `Gestion` uniquement (Salaire…, CAF, Ticket resto, Autre), sinon question ;
  - dépense sur un nom de groupe (« loisir ») → question « laquelle ? » avec les catégories du groupe.
- Hors V1 (et peut-être jamais dans Otis) : import bancaire, nouveau mois, nouvelle ligne de dépense, réparation des formules (modifient la structure de `Gestion`).
- Le classeur garde son nom (« Budget 2026 », prévu pour durer) : Otis utilise l'ID, le nom n'a pas d'effet.

## Choix techniques (agent, à signaler en fin d'étape)
- `app/connectors/sheets/budget_connector.py` + `budget_models.py` (Pydantic) : lecture des valeurs brutes (montants numériques, dates), écriture `USER_ENTERED`, ajout à la première ligne vide sous les données (comme `getLastRow()+1`). Fail-fast : onglet / en-tête / catégorie / mois introuvable → erreur qui cite la valeur attendue et les valeurs disponibles.
- Cache mémoire 3 min par onglet ; toute écriture invalide l'onglet concerné et `Gestion`.
- Outils de l'agent Gemini : `app/core/agent/tools/budget_{models,tools,registry}.py`. **Pas** exposés à l'expert Claude (coût des déclarations d'outils).
- Annuler : supprime la ligne écrite par Otis **seulement si elle est restée identique** (retrouvée par son contenu, pas par son numéro, car l'import ajoute des lignes après) ; sinon refus explicite (« modifiée depuis »).
- Tests hors ligne avec un faux classeur (comme `tests/meals_fakes.py`) ; aucun appel réel à Google dans la suite.

## Étapes
- [x] **Étape 1 — Lecture** : connecteur (catégories, tri auto, mois actif, reste total / du mois, revenus par type et par mois, échéanciers) + résolution de catégorie (Catégories → Tri auto → ambigu/inconnu). Tests unitaires sur faux classeur.
- [x] **Étape 2 — Outils de lecture de l'agent** : `get_budget_remaining`, `get_income`, `get_installments` ; consigne de l'agent (reste total par défaut, mois si demandé) ; câblage dans `factory.py`.
- [x] **Étape 3 — Écritures dépense / revenu** : `add_expense` (Débit / Swile), `add_income` (Revenus), invalidation du cache, annulation.
  - Fait (5be5728) : `add_expense` / `add_income` / `correct_budget_category`, annulation par contenu, libellés « Dernières actions », règles 23-25 de la consigne. **Non déployé** : en prod, Otis écrirait dans le vrai classeur → déploiement à l'étape 5, après validation sur une copie.
  - Constats du classeur (lecture seule, 23/11) : `Débit` a une colonne E remplie mais **sans en-tête** ; `Swile` n'a que 4 colonnes (et n'est jamais touché par l'Apps Script) ; `Revenus` n'a **aucune ligne libre** dans sa grille → Otis l'agrandit avant d'écrire ; les formules de `Gestion` lisent des colonnes ouvertes (`$A:$A`…).
  - Choix ci-dessous **validés par l'utilisateur le 24/11** (correction limitée au dernier lot : cas rare, il corrigera dans le classeur au besoin).
  - Choix agent : Swile → intitulé « Otis : … » dans Commentaires (pas de colonne Intitulé) ; date écrite en ISO (comprise par Sheets quelle que soit la langue) ; libellé obligatoire pour l'agent (à défaut, la catégorie dite) ; correction = dernière ligne budget du **dernier lot d'actions** de la conversation (journal d'annulation), donc seulement juste après l'écriture ; une ligne retrouvée par son contenu (date, montant, catégorie, commentaire, intitulé ; espaces de bord ignorés), la plus récente si deux sont identiques.
- [x] **Étape 4 — Échéanciers et dépenses multiples** : `add_installment` (mensualité arrondie au centime, échéance actuelle 0, Actif), `predeclare_split_expense` (somme des parts = total, sinon refus), annulation.
  - Fait : `add_installment` / `predeclare_split_expense` (connecteur `add_installment` / `add_split_expense`, annulation par contenu commune aux trois types de lignes), règles 26-27 de la consigne, libellés « Dernières actions ». **Non déployé** (écritures réelles → étape 5).
  - Constats (lecture seule, 24/11) : `Échéanciers` n'a **aucune ligne libre** (grille agrandie avant d'écrire) ; `Mois Début` est stocké en **date** (1er du mois, affiché « novembre 2026 ») car l'`appendRow` de l'Apps Script interprète le texte ; l'import rapproche un échéancier par **mois attendu + mensualité ±0,05 €** (pas par le nom) et une dépense multiple par **mot-clé contenu dans le libellé bancaire**, montant ±0,05 €, ±3 jours.
  - Choix agent (à valider) : mot-clé et nom **sans** préfixe « Otis : » (le mot-clé sert au rapprochement, le nom est un nom de projet) ; mois de début = mois en cours sauf mois dit (mois déjà passé sans année → l'an prochain) ; date approximative = aujourd'hui sauf date dite ; au moins 2 échéances ; catégories rapprochées comme une dépense (groupe → question) ; formats posés comme l'Apps Script (`#,##0.00 €`, « mmmm yyyy », `dd/mm/yyyy`) car une ligne ajoutée par l'API n'en hérite pas ; JSON identique à `JSON.stringify` ; annulation refusée si l'import a déjà rapproché une échéance ou traité la dépense multiple (« modifié depuis ») ; « non, c'était dans X » ne vise pas ces deux types.
- [x] **Étape 5 — Validation réelle** (accord utilisateur du 24/11 pour écrire sur la **copie** de test ; identifiant hors dépôt, script du scratchpad avec garde-fou « différent de `SPREADSHEET_BUDGET_ID` ») :
  - Copie, connecteur seul : dépense Débit, Swile, remboursement (−20), revenu (Revenus plein → grille 74 → 75), correction de catégorie, échéancier (Mois Début brut = date, affiché « novembre 2026 », mensualité 33,33), dépense multiple (formats « 50,00 € », `dd/mm/yyyy`, JSON) ; reste Course −12,34 puis rétabli ; les 7 lignes annulées par contenu, copie revenue à l'identique.
  - Copie, Gemini réel (base temporaire, sans Claude) : 7 phrases → 7 bons outils (3 à 5 s), puis annulation de chaque écriture depuis « Dernières actions ». Mot-clé « Amazon » avec majuscule : sans effet, l'import compare en minuscules (`normalizeText`).
  - Constat : un script qui enchaîne les écritures dépasse le quota Sheets de 60 lectures/min (chaque `worksheet()` de gspread relit les métadonnées) ; sans effet à l'usage vocal (quelques lectures par phrase).
  - E2E `tests/test_e2e_budget.py` : conversation complète sur un classeur plein (lecture après écriture, invalidation du cache), annulations depuis l'accueil → classeur identique à l'état initial.
  - README, SPEC ; `deploy.yml` transmettait déjà `SPREADSHEET_BUDGET_ID`. Déploiement, puis test sur téléphone (en prod, Otis écrit dans le **vrai** classeur, accepté par l'utilisateur).
  - Déployé le 24/11 (main 0329458) ; **test sur téléphone validé par l'utilisateur le 24/11**.
- [x] **Étape 5 bis — Noms de catégorie appris** (demande utilisateur du 24/11 : « Loisir Alexis » → question « lequel ? » à chaque fois). Décisions utilisateur (24/11) :
  - stockage dans la **base de l'app** (table `budget_category_aliases` : nom dit → catégorie), jamais dans `Tri auto` (l'import s'en sert : un mot court classerait mal des lignes bancaires) ;
  - apprentissage **uniquement** quand l'utilisateur répond à la question « lequel ? » (catégorie ambiguë) ; jamais sur « non, c'était dans X » (souvent une erreur de sa part) ;
  - Otis l'annonce en une phrase (« Je retiendrai que "loisir alexis", c'est Loisir Alex ») ; « oublie loisir alexis » l'efface (outil vocal) ; « Annule » juste après efface aussi l'apprentissage ;
  - s'applique à toutes les saisies et lectures (dépense, revenu, échéancier, dépense multiple, restes) ; un nom exact du classeur l'emporte toujours sur un nom appris.
  - Choix agent : question en attente gardée en mémoire par conversation (10 min) ; apprentissage seulement si la réponse est une (et une seule) des catégories proposées, toute autre réponse consomme la question ; nom appris ignoré si sa catégorie n'existe plus (ou n'est pas permise, ex. revenu).
  - Fait : table `budget_category_aliases` (`app/core/database/budget_aliases.py`), question en attente (`budget_pending.py`), rapprochement « appris », champ `nom_appris` des résultats, outil `forget_budget_alias`, annulation de l'apprentissage avec l'écriture, règle 28. Validé avec Gemini réel sur la copie (question → réponse → annonce → réutilisation → oubli).
- [ ] **Étape 6 — Repasse sur l'Apps Script** (projet séparé `~/CODE/budget`, proposée par l'utilisateur) : récupérer la version réellement déployée (`clasp pull`) et la versionner avant toute modification ; pistes à valider avec l'utilisateur : dans la fenêtre de doublon, remplacer la ligne « Otis : … » par la ligne bancaire en gardant sa catégorie ; fenêtre de ±2 jours trop courte pour certains débits CB ; lecture de `Catégories` en ignorant les catégories terminées.
- [ ] **Étape 7 — Écran Budget dans la PWA** (demande utilisateur du 24/11, **après l'étape 5**, en fin de phase ; maquette éventuelle via Claude Design) :
  - suivi : reste total de chaque catégorie de budget, tableau des totaux de dépenses (onglet `Total dépenses`), petit graphique en barres comme l'écran Sport pour rendre les restes explicites ;
  - formulaires sans passer par la voix : dépense, revenu, échéancier, dépense multiple (mêmes champs que les formulaires de l'Apps Script ; réutilisent les écritures des étapes 3-4) ;
  - à cadrer avant de coder (architecture / comportement) : endpoints REST dédiés, contenu exact du tableau, catégories proposées (liste déroulante), annulation depuis l'écran.
- Choix de l'étape 4 validés par l'utilisateur le 24/11 (y compris : mois dit déjà passé sans année → l'an prochain).
- [ ] **Idée à cadrer (utilisateur, 23/11) — Import Swile par captures d'écran** : pas d'export Swile simple → importer les dépenses Swile depuis des captures de l'appli (même principe que l'import de séances par capture, `routers/sport_screenshot.py`). Questions à trancher avant de coder : lecture des captures (Gemini vision gratuit ?), catégorie de chaque ligne (Tri auto / question), doublons avec les lignes « Otis : … » déjà dictées, relecture avant écriture.
