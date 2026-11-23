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
- [ ] **Étape 3 — Écritures dépense / revenu** : `add_expense` (Débit / Swile), `add_income` (Revenus), invalidation du cache, annulation.
- [ ] **Étape 4 — Échéanciers et dépenses multiples** : `add_installment` (mensualité arrondie au centime, échéance actuelle 0, Actif), `predeclare_split_expense` (somme des parts = total, sinon refus), annulation.
- [ ] **Étape 5 — Validation réelle** (accord explicite requis : données réelles) : lectures sur le vrai classeur ; écritures sur une **copie** du classeur partagée au compte de service (à décider avec l'utilisateur). E2E du flux voix → outil → classeur (faux classeur). README, SPEC, déploiement (variable `SPREADSHEET_BUDGET_ID` côté CD), test sur téléphone.
- [ ] **Étape 6 — Repasse sur l'Apps Script** (projet séparé `~/CODE/budget`, proposée par l'utilisateur) : récupérer la version réellement déployée (`clasp pull`) et la versionner avant toute modification ; pistes à valider avec l'utilisateur : dans la fenêtre de doublon, remplacer la ligne « Otis : … » par la ligne bancaire en gardant sa catégorie ; fenêtre de ±2 jours trop courte pour certains débits CB ; lecture de `Catégories` en ignorant les catégories terminées.
