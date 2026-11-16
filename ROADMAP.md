# Roadmap - Refonte UX/UI de la PWA

Branche : `feat/ux-redesign` (depuis `develop`). La roadmap précédente (fiabilisation du micro) est dans l'historique git de ce fichier (commit `c761bd3`).
Référence visuelle : kit `refonte-assistant-hub/refonte/` (hors git) — `styles/hub.css` (source de vérité du style), `exemple.html`, `maquettes/*.html`, `screens/*.png`.

## Cible
Plus de barre d'onglets : menu burger (`.drawer`) + accueil à bulles + sections en feuilles (`.sheet`) qui montent du bas, et une barre de saisie universelle (`.composer`) dont seul le placeholder change. La logique métier (Otis/Gemini, stockage, calculs sport, trophées) ne change pas.

## Décisions (10/11)
- Réponses texte d'Otis : la dernière s'affiche en tête de « Dernières actions » ; l'historique complet s'ouvre dans une feuille « Conversation ».
- « Dernières actions » : lues dans le journal serveur des conversations ; « Annuler » seulement sur la plus récente (le serveur n'annule que la dernière action).
- Depuis une feuille, la réponse d'Otis s'affiche en toast (en plus de la voix) et la feuille se rafraîchit.
- Le contexte de la feuille (`ui_context`) est transmis en texte et en audio, et injecté dans le prompt de l'agent.
- « Dicte ta séance » : nouvelle route qui analyse la dictée sans enregistrer, pour pré-remplir le formulaire Séance.
- L'app reste utilisable à chaque déploiement : dès le socle, toutes les sections passent en feuilles avec leur contenu actuel, puis chaque écran est rhabillé.

### Sport (décisions du 10/11)
- Types proposés (formulaire, filtres, Otis) : EF (« Endurance »), Course, Sortie longue, Vitesse, Fractionné, Renforcement. Tempo et Récup ne sont plus proposés ; les séances existantes de ces types restent telles quelles.
- Douleur : nouveaux champs en base `douleur_intensite` (0-10, vide = rien signalé) et `douleur_zone` (texte court) ; formulaire avec case « Douleur signalée » → curseur + zone ; Otis les remplit depuis la dictée. Pas de reprise de l'historique : tag « Douleur ? » déduit des remarques tant que le champ est vide.
- Vue Semaine : D+ total ajouté aux totaux de période ; jauge km-effort / plafond de la semaine affichée (S-1 + 10 %) ; badge Saine / Vigilance / Risque issu de l'alerte existante.
- Détail d'une séance : le contexte envoyé à Otis inclut la séance ouverte (« c'était 48 minutes » modifie celle-là).
- Dictée de séance : route brouillon `POST /api/v1/sport/session/draft` (audio ou texte → transcription + 1 appel Gemini en sortie structurée, rien n'est écrit) ; « Dicter une séance » ouvre d'abord le formulaire et lance l'écoute, « OK » enregistre.

### Sport — interface (décisions du 16/11)
- Dictée du formulaire : capture « à usage unique » du moteur micro existant (`captureOnce` de speech.js : mêmes réglages, pause du mot-clé), l'audio part vers la route brouillon.
- RPE et météo vides : curseur affiché « — / 10 » et rien n'est envoyé tant qu'il n'a pas été touché.
- Feuille Sport : barre d'actions seule (comme la maquette) ; la barre de saisie revient dans le détail d'une séance (« En fait c'était 48 minutes »).
- Champ « Programme » conservé dans le formulaire et affiché dans le détail.

### Trophées (décisions du 16/11)
- Feuille empilée sur Sport (‹ = retour au Sport, ✕ = tout fermer), ouverte par l'icône 🏆 et le raccourci `?action=sport_gamification`.
- 4 onglets : ⚡ En une séance (mono_session) ; 📈 Cumuls (distance, D+, temps, régularité) ; 🧙 Pop‑culture ; 🕵️ Secrets & absurdes. Dans chaque onglet, diamant et mythique derrière « Voir les légendaires 👑🪐 ». Tri : débloqués d'abord, puis progression décroissante.
- Date de déblocage (`unlocked_at`) recalculée côté serveur en rejouant l'historique (jour de la séance qui a fait basculer le badge ; rien n'est stocké ; cache mémoire à une entrée). « Tout juste débloqué » (`.just-unlocked`) = débloqué il y a 7 jours au plus. Carte : « Débloqué ✓ · 4 oct. ».
- Équivalences : champs serveur `headline` / `detail` (chiffre en gros + détail), la phrase `text` reste pour la chronique.
- Après l'écran : ~22 nouveaux trophées pop‑culture (Astérix / Mission Cléopâtre, WoW, Seigneur des Anneaux, Sanderson sans spoiler : rien d'Elantris ni de l'ère 2 de Fils-des-Brumes), 6 secrets (1er janvier, 25 décembre, vendredi 13, 42, palindrome, 29 février), 3 équivalences animaux (sterne arctique, monarque, guépard) ; Spren de la douleur déclenché sur le mot entier « dur ». Précisions utilisateur : reset du **mercredi** (serveurs EU) ; Sprens de gloire = 5 records de plus longue sortie battus (3 déjà atteints).
- Équivalences qui changent chaque jour (demande du 16/11) : grande réserve de références par famille (D+ : tour Eiffel, Mont Blanc… ; distance : marathons, GR20… ; énergie : croissants… ; animaux), tirage du jour sans répétition avant épuisement de la réserve. 4 par jour, une par famille (D+, distance, énergie, animaux). À faire avec les nouveaux trophées.
- Seuils recalibrés sur les données de prod (218 séances, 904 km, validés le 16/11) : A-38 = 38 fractionnés ; Marmite = 7 séances en 7 jours ; 12 travaux = 12 semaines d'affilée à ≥ 3 séances ; « Rome ne s'est pas faite en un jour » = 52 semaines d'affilée (remplace « Palais en 3 mois ») ; Many whelps = 50 fractionnés ; Reset du mercredi = 52 mercredis ; Réputation EF Honoré 50 / Révéré 100 / Exalté 200 ; Trois chasseurs = 217 km en 3 mois glissants ; Sprens de gloire = 15 records de plus longue sortie battus ; Fils-des-Brumes = 25 séances dans un mois ; Souffles = 50 / 200 / 600 / 1 000 / 2 000 séances ; Chull express = 20 séances à > 7:30/km sur ≥ 5 km ; Retour du roi inchangé (coupure ≥ 21 j). Mots-clés et autres seuils inchangés. Secrets de date rétroactifs.

### Tâches (décisions du 16/11)
- Sections : En retard (pastille rouge « 9 nov. »), Cette semaine (pastille verte « jeu. 19 »), Plus tard (pastille grise « 3 déc. »), Sans date, puis les groupes. Compteur du titre = tâches affichées en lignes.
- Groupes = sous-tâches Google : une tâche parente d'au moins une sous-tâche ouverte devient le titre du groupe (le connecteur lit `parent`).
- Bouton ↗ : 1re adresse http(s) des notes, sinon du titre.
- Ajout par la barre de saisie (Otis, journalisé et annulable) ; le bouton calendrier (feuille Tâches seulement, la photo y est masquée comme sur la maquette) choisit une date et une heure facultative, jointes en clair au message (« … — échéance le jeudi 19 novembre 2026 à 09:15 »).
- Heure : l'API Google Tasks ne garde que le jour → une tâche avec heure crée un événement Google Agenda de 30 min (agenda principal, rappels par défaut de l'agenda), lié par propriétés privées (`pahTask`, `pahTaskId`, `pahRappel`), sans table locale. Rappel en plus seulement s'il est demandé (« un jour avant » = 1440 min, ajouté aux rappels par défaut). Cocher supprime l'événement s'il est à venir ; « Annuler » / rouvrir le recrée. Nouveau droit OAuth `calendar.events` (consentement à refaire).
- Livraison en une fois (décision utilisateur) : rien n'est déployé avant le nouveau jeton OAuth (.env + secret GitHub).

## Étapes
- [x] **0. Socle** (déployé le 10/11, SW v31) : `hub.css`, topbar, menu burger, système de feuilles (Échap, glissé, focus rendu, empilement), barre de saisie unique déplacée dans la feuille ouverte, contexte transmis (texte + audio) et lu par l'agent, thème (préférence sinon `prefers-color-scheme`), raccourcis `?action=`, SW v31.
- [x] **1. Accueil** (déployé le 10/11, SW v33) : « Dernières actions » (+ dernière réponse d'Otis), 4 bulles (Ce soir, Sport du jour, À acheter, Prochaine tâche), feuille « Conversation ».
- [x] **2. Sport** (déployé et validé sur téléphone le 16/11, SW v35 : notes en pastilles à toucher, dictée de séance OK) : vues Semaine, Mois · Année, Séances ; détail en feuille empilée ; formulaire Séance unique (créer/modifier) avec « Dicte ta séance » (route d'analyse sans enregistrement) ; barre d'actions. Trophées : ancien rendu derrière l'icône 🏆 jusqu'à l'étape 3.
- [x] **3. Trophées** (déployé et validé sur téléphone le 16/11, SW v36) : feuille empilée, dates de déblocage, 34 nouveaux trophées (122 au total), équivalences du jour.
- [x] **4. Courses** (déployé et validé sur téléphone le 16/11, SW v37) : lecture directe `GET /api/v1/meals/shopping` (plus de question à Otis à l'ouverture), onglets Cette semaine / En attente avec compteurs d'articles restants, groupes par rayon, pastille quantité tirée du suffixe « xN », « J'ai fini mes courses » en bas de liste, menu ⋯ (Réinitialiser la semaine, Vider les achetés — ce dernier reste confié à Otis pour être journalisé et annulable), bandeau de fin restylé.
- [ ] **5. Tâches** (codé et vert le 16/11, SW v38 ; en attente du nouveau consentement OAuth avant déploiement) : sections par échéance, groupes de sous-tâches, lien, date + heure dans la barre, heure = événement Agenda.
- [ ] **6. Repas**
- [ ] **7. Second cerveau**, puis feuilles « Journal & feedback » et « Réglages & voix ».
- [ ] **8. Nettoyage** : suppression de l'ancien `style.css`, test E2E de la navigation, README.

- [ ] **9. Nouveau logo** (« Sceau du scribe », demandé le 10/11, après la refonte) : kit dans `icons/` (racine, consignes `icons/ICONES.md`) → icônes PWA remplacées (anciennes supprimées), `manifest.json` (clés `icons`, `background_color`, `theme_color` seulement), balises favicon / apple-touch-icon / theme-color du `<head>`, logo de l'appli (avatar du menu…) → `logo-otis.svg`, précache du SW + version. Rappeler à l'utilisateur de désinstaller / réinstaller la PWA.

## Plus tard (hors périmètre)
- [ ] Annuler n'importe laquelle des 3 dernières actions (aujourd'hui : seulement la plus récente, limite du serveur).
