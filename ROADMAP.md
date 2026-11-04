# Roadmap - Fiabilisation du micro de la PWA

Branche : `feat/mic-reliability` (depuis `develop`). La roadmap de l'onglet Sport est dans l'historique git de ce fichier (commit `a6fb0ba`).
Référence : SPEC Phase 6, « Pipeline STT Robuste & Pérenne » et « Déclenchement Mains-Libres & Wake Word ».

## Cible
Un micro fiable sur Chrome Android (PWA installée) : le mot-clé « Otis » se charge et réveille la dictée, la dictée part toujours au serveur, toute erreur est expliquée à l'écran, et la transcription française est juste (« ajoute du lait », « RPE à 3 »).
Hors périmètre : la conversation « speech-to-speech » temps réel.

## Chaîne actuelle (lue dans le code, 04/11)
1. **Mot-clé** : `wake_word_vosk.js` (Vosk WASM dans un worker, micro brut, grammaire « otis ») ; modèle de 42 Mo servi en flux par `/vosk/model.tar.gz`, extrait (68 Mo) dans un système de fichiers en mémoire et recopié dans IndexedDB.
2. **Dictée** : `speech.js` enregistre avec `MediaRecorder` (micro avec traitements) et une VAD maison (seuil 18, silence 2 s, inactivité 7 s). **Pas de Web Speech** (sauf repli si `MediaRecorder` manque).
3. **Envoi** : `chat_view.js` → `POST /api/v1/interact/audio` (délai client 25 s) → Gemini transcrit (et classe l'intention, résultat ignoré) → tour de l'agent (2 appels Gemini, médiane 8 s).

## Hypothèses du diagnostic statique (à confirmer sur le téléphone)
| # | Symptôme | Hypothèse | Preuve dans le code |
|---|----------|-----------|---------------------|
| V1 | Le modèle « ne se télécharge pas » | Le toast « téléchargement du modèle » s'affiche après 2 s même si le modèle est en cache : il mesure la durée du démarrage, pas un téléchargement | `speech.js`, `startWakeWordDetection` (`slowLoadTimer`) |
| V2 | Mot-clé inopérant | Au lancement de l'app, l'écoute démarre sans geste : `AudioContext.resume()` peut rester en attente indéfiniment, l'indicateur affiche « Otis à l'écoute » alors que rien n'écoute, et le flux micro reste ouvert | `wake_word_vosk.js`, `start()` |
| V3 | Chargement très long ou bloqué | Mémoire : archive 42 Mo + modèle extrait 68 Mo en mémoire + modèle dans le tas WASM, relu en entier depuis IndexedDB à chaque lancement ; un plantage du worker n'émet aucun événement écouté → attente de 120 s | `vosk.worker.js` (`downloadAndExtract`, IDBFS) |
| V4 | Mains-libres « disparu » | Désactivé par défaut et coupé automatiquement au premier échec de chargement | `config.js`, `handleWakeEngineFailure` |
| D1 | « Délai réseau dépassé », message rejoué plus tard | Délai client 25 s < transcription (jusqu'à 12 s par modèle de repli) + agent (8 à 16 s) ; le serveur continue et l'outbox rejoue → action possiblement faite deux fois | `api.js`, `stt_service.py`, `offline_outbox.js` |
| D2 | Erreur « bizarre » | Toute erreur Gemini remonte en 503 avec le texte brut de l'exception (« Échec de transcription audio : … ») | `interact.py`, `stt_service.py` |
| D3 | « Accès au microphone refusé » alors qu'il est autorisé | Toute erreur `getUserMedia` (micro occupé par Vosk, `NotReadableError`…) affiche ce message | `app.js`, `speech.js` |
| D4 | Audio pas envoyé, sans message | Enregistrement ≤ 1000 octets ignoré en silence (`console.debug`) | `speech.js`, `mediaRecorder.onstop` |
| D5 | Début de phrase perdu après le bip | Bip et ouverture du micro avec traitements simultanés ; l'ouverture peut prendre plusieurs centaines de ms sur Android | `speech.js`, `startAudioCapture` |
| D6 | « lait » → « thé », « à trois » → « Troyes » | Prompt de transcription qui demande aussi l'intention et de « corriger » la phonétique sans lexique, sur le modèle actif (souvent lite) | `stt_service.py` |

---

## Étapes d'Implémentation (chaque étape : TDD, 100 % vert)

### [ ] Étape 0 : Diagnostic sur le téléphone
- [ ] Journal du micro de l'app (`voice_diag_log.js`) : mot-clé (étapes et durées du chargement, état de l'`AudioContext`), dictée (déclencheur, ouverture du micro, VAD, raison de l'arrêt, taille), envoi (statut, durée, erreur, mise en attente). Gardé dans `localStorage`, partagé entre la PWA et Chrome.
- [ ] `audio_diag.html` : lecture et vidage de ce journal, environnement (mémoire, stockage, base IndexedDB de Vosk), téléchargement du modèle seul avec progression, `AudioContext` créé sans geste.
- [ ] Tests sur le téléphone par l'utilisateur, résultats reportés ici.

### Premiers résultats du journal (04/11, usage réel)
- **Mot-clé** : fonctionne (confiance 0,95 à 1,00, micro ouvert en 50 à 370 ms).
- **D4 confirmé, cause = bouton « maintenir »** : tap puis tap → 1re capture lancée après le relâchement (micro ouvert en 410 ms), jamais arrêtée ; la 2e (0 octet) est jetée sans message.
- **D2 confirmé et aggravé** : erreur 503 affichant l'URL Gemini **avec la clé API**. Le repli essayait 15 modèles, dont des modèles d'image à quota nul ; seule la dernière erreur (`3.7-flash`, 400) était gardée.
- **D6 reproduit** : sur 3 s de son sans parole, le prompt actuel fait « transcrire » à `flash-lite` le début du prompt (« Tu es Otis. ») ; sans le schéma d'intention, il répond `<noise>`.

### [x] Étape 1 : Correctifs urgents (décisions utilisateur du 04/11)
- [x] Clé Gemini passée en en-tête `x-goog-api-key` dans tous les appels (plus jamais dans une URL ni dans un message d'erreur).
- [x] Repli de transcription : modèles « image » exclus des candidats ; chaque échec est noté modèle par modèle dans les logs ; le téléphone reçoit un message clair (« Je n'ai pas pu transcrire ton message : quota Gemini atteint ou service surchargé… »).
- [x] Bouton hybride en mode « maintenir » : appui long = parle tant que maintenu ; appui bref (< 400 ms) = bascule, arrêt au prochain toucher ou au silence. Jamais deux captures à la fois ; un arrêt demandé pendant l'ouverture du micro s'applique dès qu'il est ouvert ; écouteurs de relâchement remplacés au lieu d'être accumulés ; « Message trop court : rien n'a été envoyé. » affiché.
- [ ] Test sur le téléphone par l'utilisateur.

### [ ] Étape 2 et suivantes : correctifs restants
Prompt de transcription (D6), délai client et rejeu (D1), message micro « refusé » (D3), bip (D5), mot-clé (V1 à V4) : à décider avec l'utilisateur.

### [ ] Comparatif STT serveur (français)
Gemini audio (en place), Gradium, Voxtral : coût, latence, qualité, recommandation. Décision utilisateur avant toute nouvelle dépendance ou API payante.

### [ ] Étape finale : test d'intégration E2E et README
