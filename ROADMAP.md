# Roadmap - Retours d'usage de l'onglet Sport (PWA)

Branche : `feat/sport-tab-ux` (la Phase 8 Agenda & Tâches est dans l'historique git de ce fichier, commit `c0d570b`). Le diagnostic du micro passe après cette feature.

## Cible
Rendre l'onglet Sport plus utile au quotidien : historique des séances paginé, menu allégé, dashboard centré sur les kilomètres et consultable sur les périodes passées (semaine -1, mois -1, saison 2025…).

## Décisions (utilisateur, 03/11)
- **Séances** : pages « Précédent / Suivant » de **30** séances, « Page X / N » ; les filtres type et statut passent côté serveur (l'API `/api/v1/sport/sessions` gère déjà `limit`, `offset`, `total` et les filtres).
- **Menu** : retrait du sous-onglet « 📸 Importer » (bouton commenté, code conservé). L'import reste accessible par le bouton « 📸 Importer capture » de l'en-tête et le coller (Ctrl+V).
- **Dashboard** : carte « Volume Total » = **km** en gros, km-effort en petit ; graphique « Évolution » en **km**, sans ligne de plafond (le plafond reste dans la carte « Sécurité & Plafond »).
- **Périodes passées** : flèches ‹ › autour du titre de la période (semaine, mois, saison) ; › grisée sur la période en cours. Aucune modification serveur : l'API accepte déjà `date` et renvoie `start_date` / `end_date`.
- Constat : le sélecteur Semaine / Mois / Année fonctionne (vérifié sur une copie de la base) ; le manque était la navigation vers les périodes précédentes.

---

## Étapes d'Implémentation (chaque étape : TDD, 100 % vert)

### [x] Étape 1 : Menu allégé
- [x] Sous-onglet « 📸 Importer » commenté ; bouton d'import de l'en-tête conservé.

### [x] Étape 2 : Séances paginées
- [x] Chargement par pages de 30 avec filtres serveur ; navigation « Précédent / Suivant », « Page X / N » ; retour sur la dernière page si la page courante est vidée (suppression).

### [x] Étape 3 : Dashboard en kilomètres
- [x] Carte Volume : km en gros, km-effort en petit ; graphique en km, sans plafond.

### [x] Étape 4 : Navigation dans les périodes passées
- [x] Flèches ‹ › : période précédente (veille de `start_date`), suivante (lendemain de `end_date`), › désactivée si la période contient aujourd'hui ; l'échelle choisie repart de la période en cours.

### [x] Étape 4 bis : Graphique selon la carte touchée & semaines autour de la sélection (retours du 03/11, après déploiement)
- [x] Cartes du dashboard cliquables : Volume → km ; Allure → hauteur = vitesse, étiquette en allure min/km ; Charge RPE → charge ; Sécurité & Plafond → km-effort avec la ligne de plafond +10 %. Changement d'indicateur sans appel réseau.
- [x] Vue Semaine : 4 semaines avant, la semaine choisie (en surbrillance), 3 après (futures comprises) ; plafond et moyenne de référence inchangés (S-1, 7 semaines passées).
- [x] Vues Mois et Année : surbrillance seulement sur la barre contenant aujourd'hui (plus de décembre surligné sur une saison passée) ; date du jour en heure de Paris (`paris_today`).

### [x] Étape 5 : Test d'intégration final
- [x] Test E2E `tests/test_e2e_sport_tab_ux.py` (séances paginées et filtrées sur toute l'histoire, saison / semaine / mois passés en km) + contrat front `tests/test_pwa_sport_tab_ux.py`.
- [ ] Test sur le téléphone.
