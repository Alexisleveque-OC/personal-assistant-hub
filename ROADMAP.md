# Roadmap - Extraction de Date Gemini Vision & Gestion Micro / Audio Focus (Ducking Musique)

Cette roadmap détaille les étapes d'implémentation pour résoudre :
1. **Extraction de date garantie sur les captures** : Rendre obligatoire le champ `date` (ainsi que `distance_km`, `duree_secondes`) dans le JSON Schema Gemini Vision pour contraindre le modèle à extraire systématiquement la date affichée (notamment `12/10/2026 - 12:55` sur Decathlon Coach).
2. **Audio Focus & Contrôle du Micro (Musique baissée en continu)** : Sur mobile, l'écoute permanente du mot-clé "Otis" (`SpeechRecognition`) réquisitionne le micro et force le système Android à baisser la musique (Spotify, Deezer) en permanence. La musique ne doit baisser QUE lorsqu'Alexis parle activement ou qu'Otis répond, avec un contrôle direct (toggle/bouton) sur l'écoute continue.

---

## Étapes d'Implémentation

### [x] Étape 1 : Rendre Obligatoires les Métriques Clés (`date`, `distance_km`, `duree_secondes`) dans `GEMINI_SPORT_VISION_SCHEMA`
- [x] Mettre à jour `GEMINI_SPORT_VISION_SCHEMA` dans `app/core/vision/sport_vision_service.py` pour inclure `date`, `distance_km`, `duree_secondes` dans `required`.
- [x] Écrire un test unitaire dans `tests/test_sport_screenshot_vision_import.py` vérifiant la présence de ces champs requis dans le schéma.
- [x] Valider l'extraction réelle sur l'image de capture Decathlon Coach.

---

### [x] Étape 2 : Révision du Micro & Audio Focus (Protection de la Musique)
- [x] Par défaut, configurer `wakeWordEnabled = false` dans `app/static/js/config.js` et `localStorage` pour ne jamais monopoliser le micro ni baisser la musique au lancement de l'application.
- [x] Transformer le badge `#wake-word-indicator` dans `app/static/index.html` et `speech.js` en interrupteur interactif direct (Toggle On/Off) :
  - Mode Bouton Micro / Push-to-Talk (Recommandé en musique) : Le micro est 100% coupé, la musique joue à plein volume. Un appui sur le micro active l'écoute + le ducking, puis relâche tout à la fin de la réponse vocale.
  - Mode Écoute Continue (Mains-libres) : Activé uniquement si l'utilisateur clique explicitement sur l'indicateur.
- [x] Garantir la libération immédiate du micro (`mediaRecorder`, `audioStream` et `SpeechRecognition`) et de tout verrou audio focus à la fin de chaque échange vocal.

---

### [x] Étape 3 : Tests de Non-Régression & Validation Globale
- [x] Lancer la suite complète de tests (`pytest -v`) : 525 tests passés avec succès à 100%.
- [x] Validation manuelle de la PWA et des imports.
