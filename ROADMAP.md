# Roadmap - Musique baissée pendant les réponses d'Otis (Android)

Branche : `feat/otis-reply-ducking` (la phase 6.9 précédente est dans l'historique git de ce fichier, commit `4eed224`)

## Constat
- Les réponses d'Otis passent par `speechSynthesis` (`speak()` dans `app/static/js/speech.js`), qui ne demande pas le focus audio sur Chrome Android : la musique (Spotify au haut-parleur) reste au même volume.
- `navigator.audioSession` (piloté par `audio_focus.js`) n'existe pas sur Chrome Android 156 (`"audioSession" in navigator` → `false`).
- Ce défaut était masqué avant la phase 6.9 par l'écoute Web Speech, qui coupait la musique en permanence.

## Cible
Baisser la musique pendant qu'Otis parle et la laisser remonter dès qu'il a fini, sans jamais la mettre en pause.

---

## Étapes d'Implémentation (chaque étape : TDD, 100 % vert)

### [x] Étape 0 : Diagnostic sur l'appareil (branche `feat/otis-reply-audio-diag`, déployée en prod les 27 et 28/10)
Modes ajoutés à `app/static/audio_diag.html`. Résultats (Android 10, Chrome 156, musique au haut-parleur) :
- **G. Synthèse seule** : musique jamais baissée.
- **H. Synthèse + micro avec traitements** (réglage de la dictée) : musique jamais baissée ; le micro rend un silence numérique (-100 dBFS) sauf sur la voix de l'utilisateur (-11 à -26 dBFS) : ni la musique ni la voix d'Otis ne sont captées.
- **I. Synthèse + clip quasi silencieux via `<audio>`, mis en pause après chaque phrase** : clip de 1 s → musique baissée mais **jamais remontée** ; clip de 30 s → musique **mise en pause** (Spotify ne repart pas seul).
- **J. Comme I (clip de 1 s), mais balise `<audio>` vidée** (`src` retiré + `load()`) après chaque phrase : **musique baissée pendant la voix et remontée après** ✅.
- **K. Dictée enregistrée** (micro et format de la dictée) : voix nette, musique absente de l'enregistrement. Ouvrir ce micro coupe la musique ~1 s (bascule probable d'Android en mode communication, même effet que la dictée de l'app).

### [x] Étape 1 : Choix de la solution (décisions utilisateur du 28/10)
- Pendant une réponse d'Otis, `AudioFocusManager` joue en boucle un clip WAV de 1 s quasi silencieux (bruit vers -70 dBFS, généré en mémoire) via une balise `<audio>`, puis la **vide** dès la fin de la réponse (fin, erreur, annulation, watchdog, passage en arrière-plan).
- La dictée n'est pas modifiée (le micro ne capte pas la musique, cf. K).
- Profondeur de la baisse : décidée par Android / Spotify, non réglable depuis le navigateur ; la mise en pause (clip long) est écartée.

### [ ] Étape 2 : Clip porteur dans `AudioFocusManager`
- [ ] Clip démarré à la demande de baisse « tts », une seule balise réutilisée, idempotent si la demande est répétée.
- [ ] Balise vidée à la libération « tts » et à la libération globale ; aucun clip pour l'enregistrement (« recording »).
- [ ] Échec de `play()` (politique d'autolecture) journalisé explicitement, la réponse vocale continue.
- [ ] Service worker v25 (module mis en cache modifié).

### [ ] Étape 3 : Test d'intégration final & validation sur l'appareil
- [ ] Test E2E : cycle complet d'une réponse d'Otis (module réel sous Node) + chaîne servie par l'application.
- [ ] Test manuel utilisateur dans la PWA : musique baissée pendant la réponse, remontée après, y compris en mains-libres (réponse déclenchée par « Otis » sans toucher l'écran).

---

## Hors Périmètre
- **Transcriptions erronées après le bip** (« ajoute lait » → « ajoute le », « ajoute du lait » → « thé ») : le mode K montre un enregistrement propre (voix nette, pas de musique). Pistes restantes : détection de fin de parole qui coupe trop tôt, démarrage de la dictée par rapport au bip, modèle de transcription Lite sur phrases courtes. Feature dédiée, en partant des échecs dans les logs de prod.
- Coupure de la musique ~1 s à l'ouverture du micro de la dictée (mode K) : jugée non gênante par l'utilisateur.
- Retrait des branches regex redondantes d'`intent_parser.py` (garantissent le retour arrière `NLU_MODE=legacy`) : uniquement sur accord explicite.
