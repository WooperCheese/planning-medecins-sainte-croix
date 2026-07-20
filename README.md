# Planning Médecins Assistants — Sainte-Croix

Application de génération automatique du planning des médecins assistants,
en remplacement du fichier Excel manuel. Voir le design complet dans
`docs/superpowers/specs/2026-07-19-planning-medecins-design.md`.

Statut : V1 (MVP) — moteur de génération + interface admin uniquement. Le
portail médecin (heures sup) et le portail RH (export paie) sont prévus en V2,
sur la même base de données.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows : .venv\Scripts\activate
pip install -r requirements.txt
```

## Premier lancement

1. Initialiser la base et créer le compte admin (mot de passe demandé en
   interactif, ou généré automatiquement et affiché une fois si tu es dans un
   environnement non interactif) :

   ```bash
   python -m app.db.seed
   ```

2. Lancer l'application :

   ```bash
   streamlit run streamlit_app.py
   ```

3. Se connecter avec le compte `admin` créé à l'étape 1.

La base est un simple fichier `planning.db` (SQLite) créé à la racine du
projet. Aucune donnée ne quitte la machine (usage local, mono-poste).

## Utilisation

- **Médecins & Cohortes** : créer les cohortes (roulements Mai-Mai / Nov-Nov),
  ajouter/désactiver les médecins assistants.
- **Congés** : déclarer les indisponibilités (congé, maladie, formation).
- **Génération** : générer le planning semaine par semaine. Une bannière
  rouge s'affiche si des postes ont dû être sacrifiés faute d'effectif.
- **Planning** : visualiser et ajuster manuellement le planning d'une semaine.

## Configuration

Tous les horaires de poste, limites horaires, règles de rotation et l'ordre
de dégradation en cas de pénurie sont centralisés dans `app/config.py`. C'est
le seul fichier à modifier pour changer un horaire, ajouter une pause ou
ajuster une règle métier.

## Tests

```bash
pip install pytest
python -m pytest -q
```

8 tests couvrent : faisabilité de base, absence de double affectation,
respect des 50h/semaine, blocs de nuit non isolés, continuité du bloc
week-end (nuit de lundi forcée + repos), et la boucle de dégradation en cas
de pénurie (ordre de sacrifice respecté).

## Prochaines étapes (V2, hors périmètre de ce MVP)

- Portail médecin assistant (lecture planning + déclaration heures sup)
- Portail RH (lecture seule + export paie)
- Gestion des taux d'activité partiels
