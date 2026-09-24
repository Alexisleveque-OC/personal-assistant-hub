# 📱 Guide d'Installation Mobile & Accès Distant (4G/5G)

Ce guide détaille la mise en place de l'accès distant à votre **Assistant Personnel Hub** depuis n'importe quel smartphone Android, en déplacement (4G / 5G / Wi-Fi extérieur).

---

## 🔒 Pourquoi un Tunnel HTTPS est Indispensable ?
1. **Accès au Microphone (STT) :** Les navigateurs mobiles modernes (Google Chrome, Firefox, Edge) bloquent strictement l'accès au microphone sur les connexions HTTP non sécurisées. Une connexion **HTTPS** avec certificat SSL valide est obligatoire.
2. **Installation PWA Native :** Les fonctionnalités de Progressive Web App (icône d'application, écran de démarrage, affichage plein écran sans barre d'URL) nécessitent un domaine HTTPS sécurisé.
3. **Sécurité Totale :** Le tunnel Cloudflare établit une liaison chiffrée de bout en bout sans ouvrir aucun port sur votre box internet personnelle.

---

## 🚀 Étape 1 : Démarrer l'Application et le Tunnel HTTPS

### 1.1 Lancer le Serveur Backend (si ce n'est pas déjà fait)
Dans un terminal PowerShell :
```powershell
.\.venv\Scripts\uvicorn app.main:app --reload --port 8000
```

### 1.2 Lancer le Tunnel Sécurisé
Dans un second terminal PowerShell :
```powershell
.\scripts\start_tunnel.ps1
```

Le script configure tout automatiquement et affiche en quelques secondes une URL publique sécurisée ressemblant à :
```text
📱 URL À OUVRIR SUR LE SMARTPHONE :
   https://xxxx-xxxx-xxxx.trycloudflare.com/app
```

---

## 📲 Étape 2 : Installer la PWA sur votre Smartphone Android

1. Sur votre smartphone, ouvrez le navigateur **Google Chrome**.
2. Saisissez l'URL affichée par le script (ex: `https://xxxx.trycloudflare.com/app`).
3. Appuyez sur le **menu de Chrome** (les 3 petits points verticaux en haut à droite).
4. Choisissez l'option **« Ajouter à l'écran d'accueil »** (ou *« Installer l'application »*).
5. Validez le nom (*Assistant Hub*).

> 🎉 **Résultat :** L'icône de l'assistant apparaît sur l'écran d'accueil de votre téléphone. En cliquant dessus, l'application s'ouvre en **plein écran**, exactement comme une application native téléchargée sur le Play Store !

---

## 🔑 Étape 3 : Configurer votre Clé d'API (Sécurité)

Si vous avez configuré une variable `API_KEY` dans votre fichier `.env` sur le serveur :
1. Sur votre smartphone dans l'application, touchez l'icône **⚙️ (Paramètres)** en haut à droite du header.
2. Dans le champ **Clé d'API (X-API-Key)**, tapez votre clé secrète.
3. Touchez **Enregistrer**.

> 💡 La clé est enregistrée dans le stockage sécurisé local (`localStorage`) de votre téléphone. Vous n'aurez plus jamais besoin de la ressaisir.

---

## 🎙️ Étape 4 : Utiliser l'Interface Mobile

* **Onglet Vocal :**
  * Touchez le **bouton Microphone central** pour dicter directement :
    * *« Qu'est-ce qu'on mange ce soir ? »*
    * *« Ajoute des pommes et du lait à la liste de courses »*
    * *« Est-ce que j'ai bien tout ? »*
  * La synthèse vocale intégrée vous répond instantanément à haute voix en français.
* **Onglet Courses :**
  * Consultez vos articles triés par rayons (*Fruits*, *Légumes*, etc.).
  * Cochez vos articles d'un simple tap en magasin (vos coches restent sauvegardées même si vous changez d'onglet).
  * Touchez le bouton **« 🏁 J'ai fini ! »** pour vérifier si vous n'avez rien oublié.
* **Onglet Repas :**
  * Affichez le menu du jour ou de **toute la semaine**.
  * Dépliez le bouton **« 🥕 Voir les ingrédients »** pour inspecter les ingrédients d'un repas.
* **Thème Clair / Sombre :**
  * Touchez le bouton ☀️ / 🌙 dans le header pour basculer entre l'ambiance **Cocooning & Botanique** et l'ambiance **Botanique Contemporain Sombre**.

---

## ⚡ Étape 5 (Optionnel) : Raccourci Écran de Verrouillage & Widget

Vous pouvez déclencher l'assistant sans même ouvrir l'application grâce à l'application gratuite et open-source **HTTP Shortcuts** (disponible sur Google Play ou F-Droid) :

1. Installez **HTTP Shortcuts** sur votre smartphone.
2. Créez un nouveau raccourci :
   * **Nom :** Assistant Hub
   * **Méthode :** `GET`
   * **URL :** `https://xxxx.trycloudflare.com/api/v1/mobile/interact?text={prompt}`
   * **En-têtes (Headers) :**
     * `X-API-Key` : `votre_clé_api`
     * `Accept` : `text/plain`
   * **Comportement de réponse :** Activer *« Lecture vocale Text-to-Speech »*.
3. Ajoutez le widget du raccourci sur votre écran d'accueil Android ou écran de verrouillage.
