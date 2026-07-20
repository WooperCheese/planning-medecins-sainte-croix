# Gestion des comptes utilisateurs — Design

**Date :** 2026-07-20
**Statut :** approuvé par l'utilisateur, prêt pour implémentation
**Sous-projet de :** "Déploiement multi-utilisateurs" (3e des 4 sous-projets : hébergement réel [fait], portail médecin [fait], gestion des comptes utilisateurs [ce document], portail RH)

## Contexte et objectif

Le portail médecin (sous-projet précédent) a volontairement exclu deux choses : le changement de mot de passe en libre-service (le médecin dépend d'une régénération admin) et une vue d'ensemble des comptes (seule la page "Médecins & Cohortes" permet de créer/régénérer un compte médecin, un par un, depuis chaque fiche). Ce sous-projet comble les deux manques : self-service password + page admin globale de gestion des comptes (création admin/médecin/rh, activation/désactivation, régénération, suppression).

## Décisions actées avec l'utilisateur

- Périmètre : les deux volets (self-service password + page admin globale), pas l'un sans l'autre.
- Règle de mot de passe self-service : 8 caractères minimum, aucune autre contrainte.
- La page admin "Utilisateurs" permet de créer directement un compte admin ou rh (pas seulement médecin), via un formulaire générique identifiant + rôle.
- Suppression définitive d'un compte autorisée (en plus de la désactivation), avec confirmation avant suppression.
- Le changement de mot de passe self-service vit sur une page dédiée "Mon compte", visible par tous les rôles connectés.
- Le changement de mot de passe self-service redemande l'ancien mot de passe (protection contre une session laissée ouverte sur un poste partagé).

## Architecture

Aucun changement de schéma de données : le modèle `User` (`username`, `password_hash`, `role`, `medecin_id`, `actif`) a déjà tout ce qu'il faut.

Deux nouvelles pages, suivant le même pattern que le reste de l'appli (une page = un fichier, garde de rôle via `require_login`) :

- `pages/7_Mon_Compte.py` : `require_login()` sans restriction de rôle — visible par admin, medecin, et rh une fois ce dernier implémenté.
- `pages/8_Utilisateurs.py` : `require_login(["admin"])`.

`app/auth/comptes.py` est refactoré pour exposer une fonction générique de création de compte, dont `creer_compte_medecin` (déjà utilisée par la page "Médecins & Cohortes") devient un cas particulier — une seule vérification d'unicité d'identifiant, pas de logique dupliquée.

Alternative écartée : dupliquer la logique de création dans une fonction séparée pour le cas générique. Rejetée pour éviter deux implémentations de la même règle d'unicité qui divergeraient avec le temps.

## Composants

### `app/auth/comptes.py`

- `creer_compte(session, username, role, medecin_id=None) -> str` (nouveau, générique) : même logique que l'actuel `creer_compte_medecin` (vérification d'unicité, génération du mot de passe, création du `User`), mais paramétrée par `role` et avec `medecin_id` optionnel.
- `creer_compte_medecin(session, medecin_id, username) -> str` : devient un wrapper (`return creer_compte(session, username, Role.MEDECIN.value, medecin_id)`). Signature et comportement inchangés pour les appelants existants (page "Médecins & Cohortes", tests existants).
- `changer_propre_mot_de_passe(session, user_id, ancien_mot_de_passe, nouveau_mot_de_passe) -> None` (nouveau) : charge le `User`, vérifie `ancien_mot_de_passe` via `verify_password`, lève `AncienMotDePasseIncorrect` si ça ne correspond pas, sinon remplace le hash. Ne modifie rien si la vérification échoue.
- `supprimer_compte(session, user_id) -> None` (nouveau) : `session.delete(session.get(User, user_id))`. Sûr côté intégrité référentielle : aucune table (`Affectation`, `Indisponibilite`, `HeureSup`) ne référence `User.id` — toutes pointent vers `Medecin.id`. Supprimer un compte de connexion n'affecte donc jamais l'historique du médecin lié.
- Nouvelle exception `AncienMotDePasseIncorrect(Exception)`.

### `pages/7_Mon_Compte.py`

Page simple, un seul formulaire : ancien mot de passe, nouveau mot de passe, confirmation du nouveau. Validations avant appel à `changer_propre_mot_de_passe` : nouveau == confirmation, nouveau ≥ 8 caractères. En cas de succès, message de confirmation (pas de déconnexion forcée — la session Streamlit reste valide, seul un futur login utilisera le nouveau mot de passe).

### `pages/8_Utilisateurs.py`

- Tableau de tous les `User` (admin, medecin, rh confondus) : identifiant, rôle, médecin lié (nom complet ou "—"), statut actif/inactif.
- Par ligne, actions : Désactiver/Réactiver (toggle direct, comme le pattern déjà utilisé pour `Medecin.actif` et `Cohorte.archivee`) ; Régénérer mot de passe (réutilise le dialogue existant `dialog_regenerer_compte`, généralisé pour fonctionner sans médecin lié) ; Supprimer (dialogue de confirmation dédié, cf. Gestion des erreurs).
- **Exception pour la propre ligne de l'admin connecté** : ni Désactiver ni Supprimer n'apparaissent, seulement "Régénérer mot de passe" (le nouveau mot de passe s'affiche à l'écran comme pour n'importe quel autre compte, donc utilisable même sur sa propre session). Ça évite qu'un admin se désactive ou se supprime lui-même par erreur et se retrouve hors de l'application.
- Bouton "+ Nouveau compte" → dialogue générique : identifiant, sélecteur de rôle (admin/medecin/rh). Si rôle = medecin, sélecteur additionnel listant uniquement les médecins n'ayant pas encore de compte (même source que le filtre déjà utilisé sur la page "Médecins & Cohortes"). Réutilise `creer_compte`.

### `streamlit_app.py`

Ajout de `pg_mon_compte` (`pages/7_Mon_Compte.py`) dans les deux branches de navigation existantes (admin et medecin), et de `pg_utilisateurs` (`pages/8_Utilisateurs.py`) uniquement dans la branche admin. Le futur portail rh (sous-projet suivant) devra aussi inclure `pg_mon_compte` dans sa propre branche.

## Gestion des erreurs

- Ancien mot de passe incorrect (page Mon Compte) → message d'erreur clair, aucune modification, pas d'exception qui remonte à l'UI.
- Nouveau mot de passe < 8 caractères, ou confirmation différente → erreur affichée avant tout appel à la base.
- Identifiant déjà pris (création générique) → réutilise `IdentifiantDejaUtilise`, déjà géré par l'UI existante.
- Suppression d'un compte → dialogue de confirmation dédié : le nom du compte à supprimer est ré-affiché en toutes lettres, un bouton "Confirmer la suppression" (rouge, via `injecter_css_bouton_danger`) doit être cliqué explicitement dans une seconde étape ; aucune suppression sur un simple clic depuis le tableau.
- Tentative de désactivation/suppression de son propre compte admin → impossible au niveau UI (boutons absents), donc pas d'erreur à gérer côté backend.

## Tests

- `changer_propre_mot_de_passe` : ancien correct → nouveau mot de passe fonctionne pour `authenticate`, ancien ne fonctionne plus. Ancien incorrect → lève `AncienMotDePasseIncorrect`, mot de passe inchangé (l'ancien fonctionne toujours).
- `creer_compte` : création d'un compte admin et d'un compte rh sans `medecin_id`. Identifiant déjà pris → lève `IdentifiantDejaUtilise`, quel que soit le rôle.
- `creer_compte_medecin` (comportement existant préservé) : les tests déjà présents dans `tests/test_portail_medecin.py` continuent de passer sans modification.
- `supprimer_compte` : le compte disparaît (`authenticate` renvoie `None` ensuite) ; si un `Medecin` était lié, la fiche médecin et son historique (`Affectation`, `Indisponibilite`, `HeureSup`) restent intacts.
- Suite pytest existante (32 tests après le portail médecin) inchangée.

## Hors périmètre (explicitement)

- Récupération de mot de passe oublié sans intervention admin (pas de flux "mot de passe oublié" par email — pas d'email dans le modèle `User`).
- Historique/audit des changements de compte (qui a créé/supprimé quoi, quand).
- Gestion fine des permissions au-delà des trois rôles existants (admin/medecin/rh).
- Portail RH (sous-projet suivant, séparé) — seule sa dépendance sur `pg_mon_compte` est anticipée ici.
