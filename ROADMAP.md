# Roadmap - Mot-clé « Otis » sans couper la musique (Android)

Branche : `feat/wake-word-audio-focus`

## Constat
- L'écoute continue du mot-clé utilise la Web Speech API (`SpeechRecognition` en `continuous`, relancée à chaque `onend` dans `app/static/js/speech.js`).
- Sur Chrome Android, cette écoute prend le focus audio : la musique (Spotify, podcast) est baissée ou coupée tant que le mains-libres est actif.
- `navigator.audioSession` (piloté par `audio_focus.js`) est sans effet sur Chrome Android.
- La dictée elle-même (`getUserMedia` + `MediaRecorder`) demande `echoCancellation`, `noiseSuppression` et `autoGainControl` à `true`.

## Cible
Garder la musique intacte pendant l'attente du mot-clé ; n'accepter une baisse du son que pendant la dictée et la réponse d'Otis.

---

## Étapes d'Implémentation (chaque étape : TDD, 100 % vert)

### [x] Étape 0 : Diagnostic sur l'appareil
- [x] Page isolée `app/static/audio_diag.html` (5 modes A à E), déployée en prod le 27/10 (main `b6de2fa`) faute d'accès USB.
- [x] Résultats (Android 10, Chrome 156, haut-parleur) :
  - **A. Web Speech continue** : Chrome termine la reconnaissance toutes les ~5 s ; chaque relance coupe la musique ~1 s.
  - **D. `getUserMedia` brut** : musique intacte ; `getSettings()` confirme les 3 traitements désactivés.
  - **E. D + `AudioContext`** : musique intacte ; le micro capte la musique du haut-parleur (~-27 dBFS) et la voix (~-18 dBFS) → un simple seuil de volume ne suffit pas, il faut un vrai moteur de mot-clé.
  - **C. `getUserMedia` avec traitements** (réglage de la dictée) : comportement anormal non qualifié.

### [x] Étape 1 : Choix de la solution (décisions utilisateur du 27/10)
- **Moteur** : Vosk dans le navigateur, fork maintenu `@lichess-org/vosk-browser` 0.0.3 (Apache 2.0, WASM ~3 Mo) + modèle `vosk-model-small-fr-0.22` (Apache 2.0, 41 Mo). Grammaire restreinte `["otis", "[unk]"]` (« otis » vérifié présent dans le vocabulaire du modèle).
- **Hébergement des assets** : téléchargés au build Docker (versions et SHA-256 figés), servis en statique, jamais commités ; mis en cache par le téléphone au premier usage.
- **Échec de chargement** : toast explicite, mains-libres désactivé, bouton micro toujours utilisable. Pas de retour à la Web Speech API (la musique n'est jamais coupée).
- **Enchaînement** : « Otis » → bip → la dictée actuelle démarre. Une commande dite d'une traite (« Otis ajoute du lait ») n'est plus prise en compte.
- **Calibrage / variantes du mot-clé** : section masquée (commentée) dans `index.html`, code JS conservé.
- Écartés : Porcupine (offre gratuite arrêtée, rapportée au 30/06/2026), openWakeWord (entraînement + modèles non commerciaux), seuil de volume + Web Speech (déclenché en permanence par la musique au haut-parleur).

### [ ] Étape 2 : Récupération des assets Vosk au build
- [ ] Script `scripts/fetch_vosk_assets.py` : télécharge le paquet npm et le modèle (URL + SHA-256 figés, échec explicite si l'empreinte diffère), réemballe le modèle en `model.tar.gz` (dossier racine `model/`), dépose le tout dans `app/static/vendor/vosk/`.
- [ ] `app/static/vendor/vosk/` ignoré par git ; étape `RUN` dans le `Dockerfile`.

### [ ] Étape 3 : Moteur de mot-clé Vosk + validation sur l'appareil
- [ ] Module `app/static/js/wake_word_vosk.js` : micro brut (sans traitements), `AudioContext`, reconnaissance restreinte, callback de détection, arrêt propre, erreurs explicites.
- [ ] Mode **F** dans la page de diagnostic utilisant ce module : temps de chargement, détection de « Otis », faux déclenchements avec musique, chauffe.
- [ ] Déploiement (accord utilisateur) et test sur le téléphone avant de brancher l'app.

### [ ] Étape 4 : Branchement dans la PWA
- [ ] `speech.js` : l'écoute du mot-clé passe sur Vosk (pause pendant dictée / réponse, arrêt en arrière-plan), « Otis » → bip → dictée.
- [ ] Échec de chargement → toast + mains-libres désactivé.
- [ ] Section calibrage / variantes masquée ; cache dédié du modèle dans le service worker (pas de re-téléchargement à chaque version du cache applicatif).

### [ ] Étape 5 : Test d'intégration final & documentation
- [ ] Test E2E du flux mot-clé → dictée → réponse.
- [ ] README mis à jour (lien Phase 6.8 compris).

---

## Hors Périmètre
- Comportement anormal du micro avec traitements (mode C, utilisé par la dictée) : à qualifier avec l'utilisateur, puis éventuellement traité dans une feature dédiée.
- Retrait des branches regex redondantes d'`intent_parser.py` (garantissent le retour arrière `NLU_MODE=legacy`) : uniquement sur accord explicite.
