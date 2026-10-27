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

### [ ] Étape 0 : Diagnostic sur l'appareil (avant tout choix de solution)
- [ ] Page de test isolée `app/static/audio_diag.html` (hors cache du service worker, non liée dans l'app) comparant 5 modes :
  - A. Web Speech continue avec relance (comportement actuel) ;
  - B. Web Speech en une seule écoute ;
  - C. `getUserMedia` avec traitements audio ;
  - D. `getUserMedia` sans traitements audio ;
  - E. D + analyse du signal (`AudioContext` + vumètre).
- [ ] Accès depuis le téléphone sans déploiement : `chrome://inspect` → Port forwarding `8000 → localhost:8000` (contexte sécurisé requis pour le micro).
- [ ] Relevé utilisateur (haut-parleur puis casque Bluetooth) : effet sur la musique (aucun / baisse / pause), reprise à l'arrêt, bip, qualité Bluetooth dégradée, valeurs `getSettings()`, réaction du vumètre, comportement écran éteint.

### [ ] Étape 1 : Choix de la solution (décision utilisateur)
- Options étudiées : détection locale (Vosk navigateur, TF.js speech-commands, openWakeWord), détection d'activité vocale + Web Speech, push-to-talk seul, app native.
- Porcupine écarté : offre gratuite arrêtée (rapportée au 30/06/2026), clé vérifiée en ligne au démarrage et visible dans un dépôt public.

### [ ] Étapes suivantes
- À détailler après la décision de l'Étape 1.
- Test d'intégration final (E2E) du flux mot-clé → dictée → réponse.

---

## Hors Périmètre
- Retrait des branches regex redondantes d'`intent_parser.py` (garantissent le retour arrière `NLU_MODE=legacy`) : uniquement sur accord explicite.
