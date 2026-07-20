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

3. Sauvegarde.
4. **Important :** un simple "rerun" de l'app ne suffit pas à prendre en
   compte un secret ajouté après le premier démarrage — le module Python qui
   lit la base reste en mémoire avec son ancienne configuration (SQLite).
   Force un vrai redémarrage : depuis la liste "My apps", clique sur **⋮** à
   côté de l'app, puis **"Reboot"**. Attends une minute avant de réessayer.

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

Pas encore d'écran "changer le mot de passe" dans l'interface (prévu avec la
gestion des comptes utilisateurs, pas encore construite). En attendant, pour
réinitialiser un mot de passe oublié ou en choisir un autre :

```bash
DATABASE_URL="<ta chaîne Neon>" python -m app.db.reset_password
```

Demande une nouvelle saisie (deux fois, pour confirmation) et met à jour
uniquement le compte `admin`.

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
- **Toujours en SQLite malgré le secret configuré** : le plus souvent, l'app
  n'a pas été redémarrée depuis (cf. note "Important" à l'étape 4) — fais un
  "Reboot" complet depuis la liste "My apps", pas juste un rechargement de
  page.
- **"Invalid format: please enter valid TOML"** dans la case Secrets : la case
  Secrets (sur share.streamlit.io) n'accepte que des lignes `CLE = "valeur"`
  — n'y colle jamais une commande de terminal entière (ça, ça va dans
  l'application Terminal de ton Mac, pas dans le navigateur).
- **`password authentication failed for user 'neondb_owner'`** : la chaîne de
  connexion copiée contenait encore les astérisques masqués. Sur Neon, clique
  d'abord sur l'icône "œil" (Show password) avant de copier.
