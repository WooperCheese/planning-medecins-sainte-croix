# Refonte design et esthétique — Design

**Date :** 2026-07-21
**Statut :** approuvé par l'utilisateur, prêt pour implémentation

## Contexte et objectif

L'appli fonctionne (hébergement réel, portails médecin/RH, gestion des comptes tous livrés) mais son habillage visuel est resté au niveau "template Streamlit par défaut" : pas d'identité propre, pas de logo, palette minimale. Ce sous-projet retravaille l'esthétique globale sans toucher à aucune fonctionnalité ni logique métier.

## Décisions actées avec l'utilisateur

- Direction : palette retravaillée + touches de branding (pas une identité graphique complète).
- Palette retenue : "Navy affirmé" — sidebar bleu nuit foncé (`#0F1F3D`) avec texte blanc, accent teal conservé (`#0f6674`), boutons navy conservés, page en fond clair neutre inchangée.
- Logo : monogramme "SC" simple, en CSS pur (pas de fichier image), pas de logo hospitalier existant à intégrer.
- Typographie : police Google Fonts Inter, avec fallback système explicite si le chargement réseau échoue.
- Les couleurs de la grille de planning (`app/ui/planning_grid.py`) restent hors périmètre : code couleur fonctionnel par poste, déjà retravaillé pour le contraste dans un sous-projet antérieur.
- Risque de lisibilité identifié et accepté : fond très foncé + texte blanc = contraste élevé, plus sûr que l'inverse. Point de vigilance retenu : le bouton "Se déconnecter" doit être visuellement distinct du nouveau fond de sidebar (bordure ou ton teal), pour ne pas se fondre dedans.

## Architecture

Changement purement présentationnel, concentré sur deux fichiers déjà existants :

- `app/ui/common.py` : CSS injecté (couleurs, police, nouveau composant logo).
- `.streamlit/config.toml` : thème natif Streamlit, dont dépendent `st.dataframe`/`st.data_editor` (glide-data-grid, ne suit pas le CSS injecté — cf. commentaire déjà présent dans ce fichier). Doit rester synchronisé avec `common.py` sous peine de grilles au thème incohérent.

Aucune nouvelle page, aucun changement de schéma de données, aucune nouvelle dépendance Python (Google Fonts se charge via une balise `<link>`/`@import` CSS, pas un package).

## Composants

### `app/ui/common.py`

- Constantes de couleur mises à jour : `COULEUR_FOND_SIDEBAR` devient `#0F1F3D` (bleu nuit foncé, était clair) ; `COULEUR_SIDEBAR_TEXTE` devient blanc/quasi-blanc (était foncé) — inversion complète de la sidebar. `COULEUR_FOND`, `COULEUR_ACCENT`, `COULEUR_BOUTON_FOND` inchangées (déjà cohérentes avec la nouvelle direction).
- Import de la police Inter via `@import url('https://fonts.googleapis.com/...')` dans le bloc `<style>` existant, avec `font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif` sur les mêmes sélecteurs déjà couverts (`.stApp`, sidebar, boutons) — le fallback garantit un rendu correct même si `fonts.googleapis.com` est bloqué par le réseau de l'hôpital.
- Nouvelle fonction `afficher_logo_sidebar() -> None` : bloc HTML/CSS (monogramme "SC" dans un carré arrondi de couleur accent + nom de l'appli à côté), injecté via `st.sidebar.markdown`. Appelée en première ligne de `afficher_sidebar_utilisateur()` (visible sur chaque page après connexion) et au début de `afficher_login()` (visible dès l'écran de connexion).
- CSS additionnel pour le bouton "Se déconnecter" dans la sidebar (sélecteur déjà ciblable via son contexte `section[data-testid="stSidebar"]`) : bordure claire ou fond teal, pour rester distinct du nouveau fond bleu nuit foncé de la sidebar.

### `.streamlit/config.toml`

Valeurs mises à jour pour matcher exactement `app/ui/common.py` : `primaryColor` reste `#0f6674` (accent teal, déjà correct) ; `font` passe de `"sans serif"` à `"Inter"` (Streamlit résout les polices Google Fonts nommées directement dans `[theme]` depuis les versions récentes — sinon fallback silencieux sur la police système, sans casse). `backgroundColor`/`secondaryBackgroundColor`/`textColor` inchangés : la zone concernée par ces réglages (grilles `st.dataframe`) reste sur fond clair/texte foncé, cohérent avec le choix de ne pas toucher aux couleurs de la grille planning.

## Gestion des erreurs

- Échec de chargement de la police Google Fonts (réseau hospitalier restrictif, hors ligne) : fallback CSS explicite sur une police système sans-serif — aucune casse visuelle, juste une police différente.
- Aucun autre cas d'erreur : changement purement CSS, pas de logique qui peut lever une exception.

## Tests

Pas de logique testable (CSS/thème pur) : la suite pytest existante (43 tests) reste inchangée et sert de garde-fou qu'aucune logique n'a été touchée par erreur. Vérification par capture d'écran après déploiement sur trois surfaces représentatives : écran de connexion (nouveau logo), page Planning (grille + sidebar foncée), un dialogue (`st.dialog`, ex. création de compte) — pour confirmer contraste et absence de régression avant de considérer le sous-projet terminé.

## Hors périmètre (explicitement)

- Couleurs de la grille de planning (`COULEURS_POSTE` dans `planning_grid.py`) — code fonctionnel, pas concerné.
- Logo réel de l'hôpital de Sainte-Croix (aucun fichier fourni ; le monogramme CSS "SC" en tient lieu).
- Toute nouvelle fonctionnalité, page, ou changement de comportement — refonte strictement visuelle.
