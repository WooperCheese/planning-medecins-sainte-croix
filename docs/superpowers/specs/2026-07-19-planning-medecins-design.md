# Application de planning des médecins assistants — Design V1 (MVP)

Date : 2026-07-19
Auteur : Maxence (avec Claude)
Statut : validé par l'utilisateur, en attente de plan d'implémentation

## 1. Contexte et objectif

Remplacer le planning Excel manuel des médecins assistants du service par une application qui génère
automatiquement le roulement à partir de la **demande** (postes fixes à pourvoir chaque jour) et d'une
liste **dynamique** de médecins actifs (l'effectif varie à chaque roulement, cycles Mai-Mai et Nov-Nov).

L'application doit être strictement modulaire : toute variable métier (horaires de poste, limites
horaires, règles de rotation, ordre de dégradation) vit dans une couche de configuration isolée, pas
dispersée dans le code métier.

## 2. Périmètre V1 (MVP) vs V2

**V1 (ce document) :**
- Moteur de génération automatique (OR-Tools CP-SAT)
- Modèle de données complet (y compris les tables nécessaires aux rôles futurs)
- Interface **admin uniquement** : gestion médecins/cohortes, saisie congés/indisponibilités,
  génération et ajustement manuel du planning
- Authentification (login/mot de passe), rôles portés par le schéma DB dès le départ
- Gestion de la pénurie avec dégradation automatique et alerte visuelle
- Mémoire glissante de 30 jours

**V2 (hors périmètre de ce spec, ajouté sur la même base de données) :**
- Portail médecin assistant (lecture seule planning + déclaration heures sup avec motif)
- Portail RH (lecture seule + export paie)

Décision : construire le MVP d'abord plutôt que tout le périmètre d'un coup, pour valider le moteur de
génération sur un vrai roulement avant d'investir dans les deux portails supplémentaires.

## 3. Déploiement

Local, mono-poste : Streamlit lancé en local (ou sur le poste du service), base SQLite en fichier local.
Aucune donnée ne transite par un serveur externe. Le modèle de données est construit avec SQLAlchemy pour
permettre une migration vers PostgreSQL le jour où l'app doit être accessible depuis plusieurs postes
(serveur interne hôpital), sans réécriture.

## 4. Stack technique

| Besoin | Choix | Justification |
|---|---|---|
| UI | Streamlit | Déploiement rapide, `st.data_editor` pour l'ajustement manuel du planning, adapté à un usage interne mono/multi-poste léger |
| Solver | Google OR-Tools (CP-SAT) | Le problème est un CSP avec contraintes combinatoires complexes (blocs de nuit consécutifs, mémoire 30 jours, dégradation). CP-SAT modélise nativement ce type de contraintes logiques, contrairement à PuLP (pensé pour l'optimisation linéaire classique) ou à une heuristique gloutonne (impossible à garantir faisable/équitable) |
| Persistance | SQLite + SQLAlchemy (ORM) | Fichier local chiffrable, migration PostgreSQL possible sans changement de code métier |
| Auth | bcrypt (hash des mots de passe) | Standard, pas de dépendance externe |
| Jours fériés | package Python `holidays`, sous-région Vaud (CH-VD) | Fériés suisses/vaudois dynamiques, traités automatiquement en régime week-end |

## 5. Architecture et arborescence

```
app/
  config.py        # POSTES, HORAIRES, LIMITES, REGLES_ROTATION, ORDRE_DEGRADATION
  db/
    models.py       # SQLAlchemy: User, Medecin, Cohorte, Affectation, Indisponibilite, HeureSup, GenerationLog
    session.py
  auth/
    auth.py          # bcrypt + vérification de rôle (décorateur require_role)
  solver/
    engine.py        # construction et résolution du modèle CP-SAT
    constraints.py   # contraintes dures (chevauchement, 50h, blocs de nuit, repos)
    objective.py     # fonction objectif d'équité (écart nuits/we entre médecins)
    degradation.py   # boucle de retry avec sacrifice de postes selon ORDRE_DEGRADATION
    calendar_ch.py   # wrapper autour du package `holidays` (CH, sous-région VD)
  ui/
    pages/           # pages Streamlit multipage : Dashboard, Génération, Médecins, Congés, Planning
  main.py            # point d'entrée, login gate
tests/
  test_constraints.py
  test_degradation.py
  fixtures/          # jeu de données ~15 médecins pour les tests
```

Principe directeur : aucun horaire, seuil ou règle de rotation ne doit apparaître ailleurs que dans
`config.py`. Ajouter une pause ou changer un horaire de poste = modifier une constante, pas le code du
solver.

## 6. Modèle de données (V1)

- **Cohorte** : période de roulement (ex. "Nov 2025 – Mai 2026"), avec dates début/fin, statut
  active/archivée.
- **Medecin** : nom, prénom, cohorte (FK), actif (bool), date d'arrivée/départ dans le service. Champ
  `taux_activite` présent (int, %) mais fixé à 100 pour tous en V1 — pas de gestion de temps partiel dans
  le calcul des quotas pour l'instant, extensible plus tard sans migration.
- **User** : login, hash bcrypt, rôle (`admin` / `medecin` / `rh` — seul `admin` a une UI en V1), FK
  optionnelle vers Medecin.
- **Indisponibilite** : médecin (FK), date_debut, date_fin, type (congé / maladie / formation),
  commentaire libre.
- **Affectation** : date, code_poste, médecin (FK), statut (`genere` / `modifie_manuellement`), flag
  `degrade` (bool, si ce poste a été maintenu malgré une pénurie ailleurs).
- **GenerationLog** : semaine générée, admin (FK), horodatage, liste JSON des postes sacrifiés le cas
  échéant (pour traçabilité et affichage de l'alerte).

## 7. Configuration des postes (extrait de `config.py`)

Structure type (pseudo-code, les valeurs viennent du cahier des charges) :

```python
POSTES_SEMAINE = [
    {"code": "POLY_MATIN", "debut": "08:00", "fin": "18:00", "duree_h": 10, "effectif": 1},
    {"code": "POLY_JOURNEE", "debut": "10:00", "fin": "20:00", "duree_h": 10, "effectif": 1},
    {"code": "APRES_MIDI", "debut": "13:00", "fin": "22:00", "duree_h": 9, "effectif": 1},
    {"code": "SERVICE_JOUR", "debut": "08:00", "fin": "18:00", "duree_h": 10, "effectif": 3},
    {"code": "GARDE_NUIT", "debut": "20:00", "fin": "08:00", "duree_h": 12, "effectif": 1},
]
POSTES_SAMEDI = [...]   # jour court, jour long, garde nuit
POSTES_DIMANCHE = [...] # jour unique, garde nuit

LIMITES = {"max_heures_semaine": 50}
REGLES_ROTATION = {
    "blocs_nuit_semaine": ["mardi", "mercredi", "jeudi"],
    "blocs_nuit_weekend": ["vendredi", "samedi", "dimanche", "lundi"],
    "repos_min_jours_apres_bloc_weekend": 2,
    "service_duree_min_semaines": 2,
    "service_duree_max_semaines": 8,
}
ORDRE_DEGRADATION = ["APRES_MIDI", "SERVICE_JOUR_REDUCTION_3_A_2"]
```

Un jour férié suisse/VD tombant un jour de semaine (lundi-vendredi) est automatiquement traité avec le
régime **samedi** (3 postes : jour court, jour long, garde de nuit). Règle simple et non ambiguë pour la
V1 ; un férié tombant un samedi ou dimanche ne change rien puisque le régime week-end s'applique déjà.
Cette règle est un paramètre isolé dans `config.py` (`REGIME_FERIE = "samedi"`), modifiable sans toucher
au solver si l'usage révèle un besoin différent.

## 8. Moteur de génération (CP-SAT)

**Horizon** : génération semaine par semaine (lundi 00:00 → dimanche 23:59).

**Variables** : booléennes `x[medecin, jour, poste] = 1` si le médecin est affecté à ce poste ce jour-là.

**Contraintes dures :**
- Un poste = exactement le nombre de médecins requis par `config.py` (1 ou 3 selon poste)
- Un médecin ne peut être affecté qu'à un seul poste par jour (unicité, pas de chevauchement)
- Max 50h de travail sur la semaine calendaire (lundi-dimanche) par médecin
- Blocs de nuit modélisés comme des **variables de bloc** (pas nuit par nuit) : un médecin est affecté au
  bloc "mar-mer-jeu" ou au bloc "ven-sam-dim-lun" dans son ensemble, jamais à une nuit isolée
- Repos obligatoire après un bloc week-end prolongé : le médecin qui termine le bloc mardi 8h ne peut pas
  travailler le mardi journée, et un nombre minimum de jours de repos consécutifs est forcé juste après
  (paramètre `repos_min_jours_apres_bloc_weekend`)

**Mémoire glissante 30 jours** : avant de lancer le solve d'une semaine, le moteur relit les affectations
réelles des 30 derniers jours en base (pas des variables libres, des constantes fixées) pour :
- Vérifier qu'aucune contrainte de repos issue de la semaine précédente n'est violée
- Déterminer le pool actuel de médecins "en service" et depuis quand, pour respecter la durée
  min (2-3 semaines) / max (1-2 mois) de présence continue en Service Jour
- Calculer le solde nuits/week-ends de chaque médecin sur la période, utilisé dans l'objectif d'équité

**Objectif (soft)** : minimiser l'écart-type du nombre de nuits et de week-ends travaillés entre tous les
médecins actifs de la cohorte, en tenant compte de l'historique.

## 9. Gestion de la pénurie (dégradation)

Boucle de résolution :
1. Tente de résoudre avec les 7 postes complets de la semaine.
2. Si infaisable → retire le poste **Après-midi** (13h-22h) de la demande, retente.
3. Si toujours infaisable → réduit le Service Jour de 3 à 2 médecins requis, retente.
4. Chaque sacrifice est écrit dans `GenerationLog` (poste, jours concernés, raison) et déclenche une
   **bannière rouge** dans l'interface admin listant précisément ce qui a été sacrifié et pourquoi, dès
   l'ouverture de la page Génération.

L'ordre de dégradation est piloté par `ORDRE_DEGRADATION` dans `config.py` — le modifier ne touche pas au
code du solver.

## 10. Authentification et rôles

- Login/mot de passe, hash bcrypt, session Streamlit.
- Schéma DB porte déjà les 3 rôles (`admin`, `medecin`, `rh`) pour éviter une migration en V2.
- V1 : seul le rôle `admin` a une interface fonctionnelle.
  - Gestion des médecins et cohortes (création, désactivation, archivage)
  - Saisie des indisponibilités (congés, maladie, formation)
  - Génération du planning (déclenchement manuel, semaine par semaine)
  - Ajustement manuel du planning généré via `st.data_editor` (avec re-vérification des contraintes
    dures avant sauvegarde, pour ne pas pouvoir créer un chevauchement ou dépasser 50h en modifiant à la
    main)
- V2 (non implémenté ici, juste préparé) : pages `medecin` (lecture planning global, déclaration heures
  sup avec motif obligatoire) et `rh` (lecture seule, export CSV/Excel heures prévues + heures sup
  déclarées).

## 11. Tests

- `test_constraints.py` : chaque contrainte dure testée isolément (chevauchement, 50h, bloc de nuit,
  repos post-bloc) sur des cas construits à la main.
- `test_degradation.py` : scénario de pénurie volontaire (effectif réduit artificiellement) pour vérifier
  que la dégradation suit bien l'ordre de priorité et que le log/alerte est correct.
- Fixture de ~15 médecins sur 4-6 semaines pour valider la faisabilité et observer la distribution
  d'équité (nuits/we) en conditions proches du réel.

## 12. Hors périmètre V1 (rappel)

- Portail médecin assistant (déclaration heures sup)
- Portail RH (export paie)
- Gestion des taux d'activité partiels dans le calcul des quotas
