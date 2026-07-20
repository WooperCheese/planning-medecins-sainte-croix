# Déploiement en ligne (Streamlit Community Cloud + Neon)

Guide pas-à-pas pour rendre l'application accessible depuis n'importe où, avec
des données persistantes. Réservé à l'admin (toi) : à faire une seule fois.

Détails du choix technique : `docs/superpowers/specs/2026-07-20-hebergement-reel-design.md`.

## Étape 1 — Créer la base de données (Neon)

1. Va sur [neon.tech](https://neon.tech) et crée un compte gratuit.
2. Crée un nouveau projet (le nom n'a pas d'importance, ex : `planning-medecins`).
3. Une fois le projet créé, va dans l'onglet **Connection Details** (ou
   **Dashboard**) et copie la **chaîne de connexion** (elle ressemble à
   `postgresql://user:motdepasse@ep-xxxx.eu-central-1.aws.neon.tech/neondb?sslmode=require`).
4. Garde cette chaîne de côté, elle sert deux fois plus bas (étapes 4 et 5).

## Étape 2 — Publier le code sur GitHub

1. Crée un compte GitHub si tu n'en as pas ([github.com](https://github.com)).
2. Crée un **nouveau dépôt public** (bouton "New repository"), par exemple
   nommé `planning-medecins-sainte-croix`. Ne coche aucune case d'initialisation
   (pas de README/gitignore générés automatiquement, le projet en a déjà).
3. Depuis le dossier du projet sur ta machine, exécute :

   ```bash
   git remote add origin https://github.com/<ton-compte>/<nom-du-depot>.git
   git branch -M main
   git push -u origin main
   ```

   (Remplace `<ton-compte>` et `<nom-du-depot>` par les tiens.)

## Étape 3 — Déployer sur Streamlit Community Cloud

1. Va sur [share.streamlit.io](https://share.streamlit.io) et connecte-toi
   avec ton compte GitHub.
2. Clique sur **"New app"**.
3. Sélectionne le dépôt créé à l'étape 2, la branche `main`, et le fichier
   principal `streamlit_app.py`.
4. Clique sur **"Deploy"**. Le premier déploiement prend une à deux minutes.

À ce stade, l'app va afficher une erreur (message rouge "Impossible de se
connecter à la base de données") — c'est normal, le secret n'est pas encore
configuré. On corrige ça à l'étape suivante.

## Étape 4 — Configurer le secret DATABASE_URL

1. Sur la page de ton app dans Streamlit Community Cloud, clique sur les
   trois points **"⋮"** puis **"Settings" → "Secrets"**.
2. Colle exactement ceci (en remplaçant par ta vraie chaîne de connexion Neon
   récupérée à l'étape 1) :

   ```toml
   DATABASE_URL = "postgresql://user:motdepasse@ep-xxxx.eu-central-1.aws.neon.tech/neondb?sslmode=require"
   ```

3. Sauvegarde. L'app redémarre automatiquement avec le nouveau secret.

## Étape 5 — Initialiser la base (une seule fois)

Toujours depuis ta machine, dans le dossier du projet, lance le script de
seed en pointant explicitement vers Neon (et non vers la base SQLite locale) :

```bash
DATABASE_URL="postgresql://user:motdepasse@ep-xxxx.eu-central-1.aws.neon.tech/neondb?sslmode=require" python -m app.db.seed
```

Ceci crée toutes les tables dans Neon et te demande un mot de passe pour le
compte `admin` (ou en génère un si tu laisses vide — il s'affiche alors une
seule fois dans le terminal, note-le).

## Étape 6 — Première connexion

1. Ouvre l'URL de ton app (visible en haut de la page Streamlit Community
   Cloud, du type `https://<nom>.streamlit.app`).
2. Connecte-toi avec `admin` et le mot de passe défini à l'étape 5.
3. Change immédiatement ce mot de passe (une fois l'interface de gestion des
   comptes disponible — en attendant, garde-le en lieu sûr).

## Mises à jour ultérieures

Toute modification poussée sur la branche `main` du dépôt GitHub redéploie
automatiquement l'app sur Streamlit Community Cloud (pas de commande
supplémentaire à lancer).

## En cas de problème

- **Message d'erreur "Impossible de se connecter à la base de données"** :
  vérifie l'orthographe exacte de `DATABASE_URL` dans les secrets (étape 4),
  et que le projet Neon est bien actif (pas en pause).
- **Écran de connexion qui refuse `admin` / mot de passe** : l'étape 5 a
  probablement été sautée ou a échoué — relance-la.
- **Toujours en SQLite malgré le secret configuré** : vérifie qu'il n'y a pas
  de faute de frappe dans le nom de la clé (`DATABASE_URL`, sensible à la
  casse) dans la page Secrets de Streamlit Cloud.
