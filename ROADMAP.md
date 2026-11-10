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

## Étapes
- [x] **0. Socle** (déployé le 10/11, SW v31) : `hub.css`, topbar, menu burger, système de feuilles (Échap, glissé, focus rendu, empilement), barre de saisie unique déplacée dans la feuille ouverte, contexte transmis (texte + audio) et lu par l'agent, thème (préférence sinon `prefers-color-scheme`), raccourcis `?action=`, SW v31.
- [x] **1. Accueil** (déployé le 10/11, SW v33) : « Dernières actions » (+ dernière réponse d'Otis), 4 bulles (Ce soir, Sport du jour, À acheter, Prochaine tâche), feuille « Conversation ».
- [ ] **2. Sport** : vues Semaine, Mois · Année, Séances ; détail en feuille empilée ; formulaire Séance unique (créer/modifier) avec « Dicte ta séance » (route d'analyse sans enregistrement) ; barre d'actions.
- [ ] **3. Trophées** : icône 🏆 de l'en-tête, `.is-locked`, `.just-unlocked`.
- [ ] **4. Courses**
- [ ] **5. Tâches**
- [ ] **6. Repas**
- [ ] **7. Second cerveau**, puis feuilles « Journal & feedback » et « Réglages & voix ».
- [ ] **8. Nettoyage** : suppression de l'ancien `style.css`, test E2E de la navigation, README.

- [ ] **9. Nouveau logo** (« Sceau du scribe », demandé le 10/11, après la refonte) : kit dans `icons/` (racine, consignes `icons/ICONES.md`) → icônes PWA remplacées (anciennes supprimées), `manifest.json` (clés `icons`, `background_color`, `theme_color` seulement), balises favicon / apple-touch-icon / theme-color du `<head>`, logo de l'appli (avatar du menu…) → `logo-otis.svg`, précache du SW + version. Rappeler à l'utilisateur de désinstaller / réinstaller la PWA.

## Plus tard (hors périmètre)
- [ ] Annuler n'importe laquelle des 3 dernières actions (aujourd'hui : seulement la plus récente, limite du serveur).
