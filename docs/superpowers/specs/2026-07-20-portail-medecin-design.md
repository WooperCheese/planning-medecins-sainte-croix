# Portail médecin — Design

**Date :** 2026-07-20
**Statut :** approuvé par l'utilisateur, prêt pour implémentation
**Sous-projet de :** "Déploiement multi-utilisateurs" (2e des 4 sous-projets : hébergement réel [fait], portail médecin [ce document], portail RH, gestion des comptes utilisateurs)

## Contexte et objectif

Le rôle `medecin` existe déjà dans le schéma RBAC (`app/auth/auth.py`, `Role` enum) mais n'a jamais eu d'interface. Ce sous-projet donne aux médecins assistants un accès en ligne, autonome, à trois choses : leur planning (et celui de l'équipe), la déclaration de leurs propres congés, et la déclaration de leurs heures supplémentaires.

## Décisions actées avec l'utilisateur

- Création des comptes médecin : action manuelle admin (pas d'auto-inscription), depuis la page "Médecins & Cohortes".
- Fonctionnalités incluses : consultation du planning de toute l'équipe (mois au choix), déclaration de congés/indisponibilités, déclaration d'heures supplémentaires.
- Congés déclarés par un médecin : passent par un statut `en_attente`, validés/refusés par l'admin avant de compter dans la génération du planning.
- Heures supplémentaires : simple journal, pas de validation, pas d'interface admin de consultation dans ce sous-projet.
- Vue planning : lecture seule, réutilise le composant "vue par médecin" déjà construit pour la page admin.

## Architecture

Navigation adaptée au rôle : `streamlit_app.py` construit la liste de pages Streamlit selon le rôle de l'utilisateur connecté, au lieu d'une liste fixe.

```
Connexion admin  → Accueil, Médecins & Cohortes, Congés, Planning (inchangé)
Connexion medecin → Accueil, Mon Planning, Mes Congés & Heures Sup (nouveau)
```

Alternatives écartées : logique conditionnelle `if role == ...` dans des pages partagées (mélange les responsabilités, contraire à l'organisation actuelle en fichiers par page) ; application Streamlit séparée pour les médecins (complexité de déploiement disproportionnée pour ce volume d'utilisateurs).

## Composants

### `app/db/models.py`

- Nouvel enum `StatutIndisponibilite` (`en_attente`, `validee`, `refusee`).
- `Indisponibilite.statut: Mapped[str]`, défaut `"validee"` (préserve le comportement actuel pour les saisies admin sans migration de données à faire : les lignes existantes restent valides via la valeur par défaut).

### `app/auth/comptes.py` (nouveau module)

Logique de création/régénération de compte médecin, séparée de `app/db/seed.py` (qui reste dédié au tout premier compte admin) :

- `creer_compte_medecin(session, medecin_id, username) -> str` : crée un `User` (role=`medecin`, lié au `medecin_id`), génère un mot de passe aléatoire (`secrets.token_urlsafe`), retourne le mot de passe en clair (à afficher une seule fois, jamais stocké).
- `regenerer_mot_de_passe(session, user_id) -> str` : même principe pour un compte existant.

Réutilisé à la fois par la nouvelle UI et potentiellement par un futur script en ligne de commande (même pattern que `reset_password.py`).

### `app/solver/history.py`

`indisponibilites_par_medecin` (déjà fonction publique, utilisée par le solveur ET par la vue planning) : ajoute `.filter(Indisponibilite.statut == StatutIndisponibilite.VALIDEE.value)`. Point d'impact unique — tous les appelants (génération CP-SAT, vue par médecin admin, nouvelle vue par médecin côté portail) héritent automatiquement du filtre.

### `pages/1_Medecins_et_Cohortes.py`

Sur chaque fiche médecin : si `medecin.id` n'a pas de `User` associé, bouton "Créer un accès de connexion" (ouvre un `st.dialog`, propose un identifiant par défaut modifiable, affiche le mot de passe généré une seule fois après création). Si un compte existe déjà, bouton "Régénérer le mot de passe" à la place (même pattern d'affichage unique).

### `pages/2_Conges.py`

Nouvelle section "En attente de validation" : liste les `Indisponibilite` avec `statut == en_attente`, un bouton Approuver et un bouton Refuser par ligne (changent simplement le `statut`).

### Nouvelles pages médecin

- `pages/5_Mon_Planning.py` : sélecteur mois/année (identique à la page admin), affiche `construire_grille_par_medecin` / `styliser_grille_par_medecin` en lecture seule pour tous les médecins actifs — pas de génération, pas d'édition. `require_login(["medecin"])`.
- `pages/6_Mes_Conges_Et_Heures.py` : `st.tabs(["Mes congés", "Mes heures sup"])`.
  - Onglet congés : formulaire de déclaration (dates, type, commentaire) → statut `en_attente` ; liste des déclarations passées avec leur statut actuel.
  - Onglet heures sup : formulaire (date, nombre d'heures, motif) → écrit directement dans `HeureSup` ; liste des déclarations du médecin.
  - `require_login(["medecin"])`.

### `streamlit_app.py`

Après le contrôle de connexion, construction conditionnelle de la liste passée à `st.navigation()` selon `st.session_state["user"]["role"]`. Le message d'accueil générique ("Seul le rôle admin...") est retiré et remplacé par un contenu adapté au rôle courant.

## Gestion des erreurs

- Tentative de création d'un compte médecin avec un identifiant déjà pris → message d'erreur clair, pas de crash (contrainte `unique` déjà présente sur `User.username`).
- Médecin sans compte essayant de se connecter → déjà géré par l'écran de connexion existant ("Identifiant ou mot de passe incorrect").
- Admin approuvant/refusant une demande de congé déjà traitée (double clic) → opération idempotente, pas d'erreur si le statut a déjà changé entre-temps.

## Tests

- Création de compte médecin : vérifie que le `User` est bien créé avec le bon rôle et lié au bon médecin, que le mot de passe généré fonctionne pour l'authentification.
- Régénération de mot de passe : l'ancien mot de passe ne fonctionne plus, le nouveau fonctionne.
- `indisponibilites_par_medecin` avec un mélange de statuts : seules les lignes `validee` sont retournées.
- Écriture/lecture d'une déclaration `HeureSup` par un médecin.
- Suite pytest existante (26 tests) inchangée.

## Hors périmètre (explicitement)

- Auto-inscription des médecins (comptes toujours créés par l'admin).
- Interface admin de consultation/export des heures supplémentaires.
- Changement de mot de passe en libre-service par le médecin lui-même (reste une régénération admin).
- Échange de garde entre médecins, notifications, ou tout ce qui dépasse consultation + déclaration.
- Portail RH (sous-projet suivant, séparé).
