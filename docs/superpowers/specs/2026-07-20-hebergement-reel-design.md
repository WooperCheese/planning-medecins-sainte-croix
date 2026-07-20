# Hébergement réel de l'application Planning Médecins — Design

**Date :** 2026-07-20
**Statut :** approuvé par l'utilisateur, prêt pour implémentation
**Sous-projet de :** "Déploiement multi-utilisateurs" (1er des 4 sous-projets identifiés : hébergement réel, portail médecin, portail RH, gestion des comptes utilisateurs — traités séparément)

## Contexte et objectif

L'application tourne aujourd'hui uniquement en local sur la machine de l'utilisateur (Streamlit + SQLite). L'objectif de ce sous-projet est de la rendre accessible depuis n'importe où, avec des données qui survivent aux redémarrages, sans dépendre de l'infrastructure de l'hôpital (l'utilisateur quitte Sainte-Croix pour la clinique de Genolier en novembre 2026 — un hébergement lié à l'employeur actuel poserait un problème de continuité).

Ce document ne couvre QUE l'hébergement technique. Les portails médecin/RH et la gestion multi-comptes restent des sous-projets séparés, à spécifier ensuite.

## Décisions actées avec l'utilisateur

- Hébergement : **Streamlit Community Cloud** (gratuit, déploiement depuis GitHub, HTTPS automatique en `*.streamlit.app`).
- Persistance des données : **Neon** (Postgres gratuit externe), car le système de fichiers de Streamlit Community Cloud est éphémère (SQLite serait effacée à chaque redéploiement/réveil de l'app).
- Dépôt de code : **GitHub public** (le code source est visible publiquement ; les données — médecins, plannings, mots de passe hachés — restent privées dans Neon et ne sont jamais exposées).
- Aucune donnée réelle à migrer : la base locale actuelle ne contient que des données de test, on repart d'une base neuve.
- HTTPS : géré nativement par Streamlit Community Cloud, aucune configuration à faire (le sujet Caddy/sslip.io envisagé pour une hypothèse VPS est devenu sans objet).

## Architecture

```
Navigateur (utilisateur)
      │  HTTPS (géré par Streamlit Cloud)
      ▼
Streamlit Community Cloud
  - exécute streamlit_app.py depuis le dépôt GitHub public
  - lit le secret DATABASE_URL (interface Streamlit Cloud, jamais dans le code)
      │  connexion SQLAlchemy (psycopg2)
      ▼
Neon (Postgres géré, offre gratuite)
  - stocke Cohorte, Medecin, User, Indisponibilite, Affectation, HeureSup, GenerationLog
```

En local (développement + tests), rien ne change : SQLite via `PLANNING_DB_PATH`, comportement actuel préservé à l'identique.

## Composants modifiés

### `app/db/session.py`

Résolution de l'URL de base, dans cet ordre de priorité :

1. `st.secrets["DATABASE_URL"]` si un fichier de secrets Streamlit est présent et contient cette clé (cas Streamlit Community Cloud, où les secrets sont toujours configurés côté plateforme).
2. Variable d'environnement `DATABASE_URL` (utile pour lancer le script de seed en local contre Neon, cf. étape 5 du déploiement).
3. SQLite via `PLANNING_DB_PATH` — comportement actuel, utilisé par les tests et le développement local sans configuration supplémentaire.

L'accès à `st.secrets` est protégé par un `try/except` : en l'absence de tout fichier `secrets.toml` (cas des tests pytest, où ce fichier n'existe pas et n'est pas committé), l'accès échoue silencieusement et la résolution passe à l'étape suivante — aucun changement de comportement pour la suite de tests existante.

`connect_args={"check_same_thread": False}` (spécifique à SQLite) n'est passé à `create_engine` que si l'URL résolue commence par `sqlite:///`.

Compromis assumé : `session.py` importe désormais `streamlit` (léger couplage de la couche base de données à l'UI). Justifié ici par la taille réduite du projet — introduire une indirection supplémentaire (injection de config, lazy engine) serait disproportionné pour ce besoin.

### `requirements.txt`

Ajout de `psycopg2-binary` (driver Postgres pour SQLAlchemy).

### `.gitignore`

Ajout de `.streamlit/secrets.toml` (le secret ne doit jamais être committé ; il est saisi uniquement dans l'interface Streamlit Community Cloud).

### `streamlit_app.py`

`init_db()` entouré d'un `try/except` : en cas d'échec de connexion à la base (URL mal formée, base injoignable), affichage d'un `st.error()` clair au lieu d'un traceback brut, puis `st.stop()`.

### Documentation

Nouveau fichier `docs/DEPLOIEMENT.md` : guide pas-à-pas avec les commandes exactes (création compte Neon, création dépôt GitHub, push, déploiement Streamlit Cloud, configuration du secret, lancement du script de seed en pointant vers Neon, première connexion).

## Flux de déploiement (étapes utilisateur)

1. Créer un compte Neon, créer un projet, récupérer la chaîne de connexion Postgres.
2. Créer un dépôt GitHub public ; le code est déjà prêt (git initialisé côté agent) — l'utilisateur crée le dépôt vide et pousse.
3. Créer un compte Streamlit Community Cloud (connexion via GitHub), déployer l'app en pointant vers le dépôt et `streamlit_app.py`.
4. Dans les secrets de l'app Streamlit Cloud, renseigner `DATABASE_URL` avec la chaîne de connexion Neon.
5. En local, lancer une fois `DATABASE_URL=<chaîne Neon> python -m app.db.seed` pour créer les tables et le compte admin initial dans Neon.
6. Se connecter à l'URL fournie par Streamlit Cloud, changer immédiatement le mot de passe admin.

## Gestion des erreurs

- `DATABASE_URL` absente ou mal formée au démarrage de l'app déployée → message d'erreur explicite affiché à l'écran plutôt qu'un traceback, avec indication de vérifier les secrets Streamlit Cloud.
- Étape de seed oubliée → écran de connexion affichant "identifiants invalides" pour toute tentative ; pas de crash, juste un rappel dans le guide de déploiement.
- Base Neon temporairement injoignable (maintenance, quota dépassé) → erreur de connexion SQLAlchemy remontée via le même `try/except`, message clair plutôt qu'un traceback.

## Tests

- Suite pytest existante inchangée : continue d'utiliser SQLite via `PLANNING_DB_PATH`, aucun test ne touche à Neon (hors de portée du bac à sable de développement).
- Nouveau test unitaire sur la fonction de résolution d'URL de `session.py` : vérifie qu'en l'absence de secret et de variable d'environnement `DATABASE_URL`, elle retombe bien sur SQLite (comportement de non-régression).

## Sécurité — état des lieux, pas de travail supplémentaire dans ce sous-projet

- HTTPS géré automatiquement par Streamlit Community Cloud (certificat sur le sous-domaine `*.streamlit.app`).
- Code source public sur GitHub, mais aucune donnée ni secret n'y est exposé (mots de passe hachés bcrypt en base Neon, jamais dans le code).
- Un seul compte admin existe pour l'instant. Les comptes médecin/RH et leurs portails associés sont un sous-projet distinct, non traité ici.

## Hors périmètre (explicitement)

- Portail médecin, portail RH.
- Création de comptes pour de vrais médecins/RH.
- Migration de données réelles (aucune donnée réelle n'existe à ce stade).
- Nom de domaine personnalisé (le sous-domaine `*.streamlit.app` fourni par la plateforme suffit pour ce sous-projet).
