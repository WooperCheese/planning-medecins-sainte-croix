# Portail RH — Design

**Date :** 2026-07-21
**Statut :** approuvé par l'utilisateur, prêt pour implémentation
**Sous-projet de :** "Déploiement multi-utilisateurs" (4e et dernier des 4 sous-projets : hébergement réel [fait], portail médecin [fait], gestion des comptes utilisateurs [fait], portail RH [ce document])

## Contexte et objectif

Le rôle `rh` existe dans le schéma RBAC depuis la V1 mais n'a jamais eu d'interface. Le spec initial (`2026-07-19-planning-medecins-design.md`) anticipait déjà sa forme : "lecture seule, export CSV/Excel heures prévues + heures sup déclarées". Ce sous-projet livre cette interface : consultation du planning de l'équipe et export Excel des heures pour la paie.

## Décisions actées avec l'utilisateur

- Périmètre : lecture seule (aucune validation, aucune modification) — planning + export paie, conforme au spec initial.
- Format d'export : Excel (.xlsx) uniquement.
- Niveau de détail de l'export : total par médecin (heures prévues + heures sup déclarées) sur le mois choisi, pas de détail ligne par ligne.
- Deux pages séparées (Planning / Export Paie) plutôt qu'une page à onglets, cohérent avec le découpage par responsabilité déjà en place ailleurs dans l'appli (Planning, Congés, Médecins sont des pages admin distinctes).
- Calcul des heures prévues basé sur la config des postes déjà existante (`PosteConfig.duree_h` dans `app/config.py`), aucune nouvelle source de vérité.

## Architecture

Deux nouvelles pages, suivant le pattern déjà établi (une page = un fichier, garde de rôle via `require_login`) :

- `pages/9_Planning_RH.py` : `require_login(["rh"])`.
- `pages/10_Export_Paie.py` : `require_login(["rh"])`.

Nouveau module `app/rh/paie.py` : logique de calcul des heures et de génération de l'export, séparée de l'UI (testable sans Streamlit, même pattern que `app/auth/comptes.py`).

Alternative écartée : une seule page à onglets (`st.tabs`, comme "Mes Congés & Heures Sup" côté médecin). Rejetée ici parce que Planning (vue live, consultée régulièrement) et Export Paie (action ponctuelle, mensuelle) sont deux usages assez différents pour justifier deux pages distinctes — contrairement aux congés/heures sup médecin qui sont deux formulaires de déclaration du même type.

## Composants

### `app/rh/paie.py` (nouveau module)

- `_duree_par_code_poste() -> Dict[str, int]` : fusionne `POSTES_SEMAINE`, `POSTES_SAMEDI`, `POSTES_DIMANCHE` (`app/config.py`) en un dictionnaire `code -> duree_h`. Les codes partagés entre listes (ex : `GARDE_NUIT`) ont déjà la même durée dans les trois listes.
- `heures_prevues_par_medecin(session, medecins, premier_jour, dernier_jour) -> Dict[int, float]` : somme, pour chaque médecin, la durée des `Affectation` dont la date tombe dans la période, via le lookup ci-dessus.
- `heures_sup_par_medecin(session, medecins, premier_jour, dernier_jour) -> Dict[int, float]` : somme, pour chaque médecin, `HeureSup.nb_heures` sur la période.
- `generer_export_excel(medecins, heures_prevues, heures_sup) -> bytes` : construit un `pandas.DataFrame` (colonnes : Médecin, Heures prévues, Heures sup, Total) et le sérialise en `.xlsx` en mémoire (`BytesIO` + `DataFrame.to_excel(engine="openpyxl")`), retourne les bytes prêts pour `st.download_button`.

### `pages/9_Planning_RH.py`

Copie du pattern de `pages/5_Mon_Planning.py` (sélecteur mois/année, `construire_grille_par_medecin` / `styliser_grille_par_medecin` / `construire_legende_html`, lecture seule) — seul le rôle exigé change (`rh` au lieu de `medecin`).

### `pages/10_Export_Paie.py`

Sélecteur mois/année (même composant que les autres pages). Récupère les médecins actifs, appelle `heures_prevues_par_medecin` et `heures_sup_par_medecin`, affiche un `st.dataframe` des totaux (une ligne par médecin + une ligne total général). Bouton `st.download_button("Télécharger l'export Excel", data=generer_export_excel(...), file_name="paie_{annee}_{mois:02d}.xlsx")`.

### `streamlit_app.py`

Nouvelle branche `role_courant == "rh"` dans la construction de la liste de pages : Accueil, Planning, Export Paie, Mon Compte (`pg_mon_compte`, déjà défini pour les autres rôles, cf. `2026-07-20-gestion-comptes-design.md`). `page_accueil()` : ajout d'un message dédié au rôle `rh` (remplace la branche générique `else`).

### `requirements.txt`

Ajout de `openpyxl` — nécessaire au moteur `to_excel` de pandas (pandas seul ne suffit pas à écrire du `.xlsx`).

## Gestion des erreurs

- Aucun médecin actif → avertissement, comme les pages Planning existantes (admin, médecin).
- Mois sans aucune affectation ni heure sup (ex : mois futur) → totaux à 0 pour chaque médecin, export généré quand même (fichier `.xlsx` valide, valeurs à 0) — pas traité comme une erreur.
- Poste avec un code absent du lookup de durées (ne devrait pas arriver, la config est la source unique) → aucune gestion spéciale : si `config.py` est modifié un jour sans y ajouter la durée d'un nouveau poste, l'erreur `KeyError` remontera explicitement plutôt que de silencieusement compter 0h, pour éviter une paie sous-évaluée sans avertissement.

## Tests

- `heures_prevues_par_medecin` : jeu d'`Affectation` connu sur plusieurs postes/médecins → total correct par médecin, sur la bonne période (exclut les affectations hors période).
- `heures_sup_par_medecin` : jeu de `HeureSup` connu → total correct par médecin, sur la bonne période.
- `generer_export_excel` : fichier généré relu avec `pandas.read_excel` → colonnes et valeurs attendues.
- Suite pytest existante (40 tests) inchangée.

## Hors périmètre (explicitement)

- Export CSV (Excel seul, comme acté avec l'utilisateur).
- Export détaillé ligne par ligne (affectation par affectation) — seulement les totaux mensuels par médecin.
- Toute action de validation ou modification par le rôle RH (reste strictement lecture seule + export).
- Historique des exports générés (pas de traçabilité de qui a exporté quoi, quand).
