# Roadmap Fix : Isolation Totale des Tests & Zéro Effet de Bord sur Google Sheet (`fix/test-isolation-zero-side-effects`)

> **Règles d'or (AGENTS.md) :**
> - Chaque étape doit être validée **manuellement et explicitement par l'utilisateur** avant de passer à la suivante.
> - La suite de tests automatisés (`pytest`) doit être à **100% au vert** à chaque étape.
> - Tout nouveau code ou correctif est développé en **TDD Strict** (Phase Rouge $\rightarrow$ Phase Verte $\rightarrow$ Refactor).
> - Zéro commit prématuré sans test préalable et validation utilisateur.

---

## Problème Identifié

Lors de l'exécution de la suite de tests automatisés en local :
1. `tests/test_e2e_mobile_voice_flow.py` simulait l'ajout vocal de bananes (`"Ajoute des bananes à la liste de courses"`) en appelant l'API sans bouchonner (mocker) le connecteur, ce qui écrivait directement dans la vraie feuille `Liste_Attente` du Google Sheet de l'utilisateur.
2. `tests/test_e2e_meals_shopping.py` (`test_e2e_shopping_item_lifecycle_live`) insérait un article de test réel (`Café test E2E <timestamp>`) sur la feuille de production.
3. `tests/conftest.py` ne verrouillait pas par défaut l'accès au Google Sheet de production pour l'ensemble de la suite de tests.

---

## Étapes de Résolution

| Étape | Description | Statut | Validation Utilisateur | Tests Automatisés |
| :--- | :--- | :---: | :---: | :---: |
| **Étape 1** | **Garde-fou global dans `tests/conftest.py`** : injection automatique d'un connecteur mock in-memory pour tous les endpoints API (`/api/v1/interact`, `/api/v1/mobile/interact`). | 🟢 Réalisé | Prêt pour validation | ✅ Validé par `test_test_isolation.py` |
| **Étape 2** | **Isolation complète de `test_e2e_mobile_voice_flow.py`** : validation E2E du parcours mobile 100% in-memory sans aucune écriture distante. | 🟢 Réalisé | Prêt pour validation | ✅ 100% vert en 0.32s |
| **Étape 3** | **Sécurisation des tests E2E dans `test_e2e_meals_shopping.py`** : classeur in-memory complet et ultra-réaliste pour tester le cycle de vie sans aucune mutation du sheet réel. | 🟢 Réalisé | Prêt pour validation | ✅ 100% vert en 0.15s |
| **Étape 4** | **Nettoyage de la feuille réelle `Liste_Attente`** : suppression des 2 lignes de test résiduelles (`Café test e2e` et `Bananes`) avec accord utilisateur. | 🟢 Validé | ✅ Réalisé avec succès | Feuille 100% propre |
| **Étape 5** | **Test d'intégration global de non-régression** : exécution de la suite complète (170 tests) en vérifiant que le Google Sheet réel n'est plus jamais touché en écriture. | 🟢 Validé | ✅ Validé par l'utilisateur | ✅ 170/170 tests verts en 11s |
