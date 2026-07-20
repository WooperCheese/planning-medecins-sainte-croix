"""
Page Planning : génération automatique (CP-SAT) + visualisation colorée +
édition manuelle du planning MENSUEL, sous forme de grille pivot, avec deux
vues (onglets) : par poste et par médecin.

100% compatible Python 3.9 : Optional[...] partout, jamais de `X | None`.
"""

from __future__ import annotations

import datetime

import streamlit as st
from sqlalchemy.exc import IntegrityError

from app.db.models import Affectation, Medecin, StatutAffectation
from app.db.session import get_session
from app.solver.engine import jours_du_mois
from app.solver.generation import generer_mois, reinitialiser_mois
from app.solver.history import indisponibilites_par_medecin
from app.solver.validation import valider_grille_manuelle
from app.ui import planning_grid as grille
from app.ui.common import (
    afficher_sidebar_utilisateur,
    injecter_css_bouton_danger,
    injecter_theme,
    require_login,
)

MOIS_LABELS_FR = [
    "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
]

injecter_theme()
user = require_login(["admin"])
afficher_sidebar_utilisateur()

st.title("Planning mensuel")

st.markdown(grille.construire_legende_html(), unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# 1. Sélection du mois
# ---------------------------------------------------------------------------

col_mois, col_annee = st.columns([2, 1])
aujourd_hui = datetime.date.today()
mois = col_mois.selectbox("Mois", list(range(1, 13)), index=aujourd_hui.month - 1, format_func=lambda m: MOIS_LABELS_FR[m - 1])
annee = col_annee.number_input("Année", min_value=2020, max_value=2100, value=aujourd_hui.year, step=1)

jours = jours_du_mois(annee, mois)
cle_mois = "{}_{}".format(annee, mois)
st.caption(
    "Mois généré : {} → {} ({} jours).".format(
        jours[0].strftime("%d.%m.%Y"), jours[-1].strftime("%d.%m.%Y"), len(jours)
    )
)

# ---------------------------------------------------------------------------
# 2. Génération automatique (CP-SAT) + Réinitialisation
# ---------------------------------------------------------------------------

col_generer, col_reset = st.columns([2, 1])

with col_generer:
    if st.button("Générer le planning du mois (CP-SAT)", type="primary"):
        resultat = None
        with st.spinner("Résolution en cours (peut prendre jusqu'à une minute sur un mois complet)..."):
            try:
                with get_session() as session:
                    resultat = generer_mois(session, annee, mois, user["username"])
            except IntegrityError:
                st.error(
                    "Conflit en base de données : des créneaux existent déjà pour ce mois et "
                    "entrent en collision avec la nouvelle génération. Clique sur "
                    "'Réinitialiser ce mois' ci-contre, puis relance la génération."
                )

        if resultat is not None:
            if not resultat.faisable:
                st.error(
                    "Génération impossible même après application de toutes les mesures de "
                    "dégradation disponibles. Effectif probablement insuffisant ce mois-ci "
                    "— intervention manuelle requise."
                )
            elif resultat.postes_sacrifies:
                st.error(
                    "⚠️ Planning généré, mais **avec dégradation** : postes sacrifiés ce "
                    "mois pour rendre la génération possible :\n\n"
                    + "\n".join("- {}".format(s) for s in resultat.postes_sacrifies)
                )
            else:
                st.success("Planning généré sans aucune dégradation.")

with col_reset:
    cle_container_reset = "zone_reset_{}".format(cle_mois)
    injecter_css_bouton_danger(cle_container_reset)
    with st.container(key=cle_container_reset):
        cle_confirmation = "confirmer_reset_{}".format(cle_mois)
        if not st.session_state.get(cle_confirmation, False):
            if st.button("🗑️ Réinitialiser ce mois", key="btn_reset_{}".format(cle_mois)):
                st.session_state[cle_confirmation] = True
                st.rerun()
        else:
            st.warning(
                "Ceci supprime DÉFINITIVEMENT toutes les affectations de {} {} "
                "(générées ET modifiées manuellement).".format(MOIS_LABELS_FR[mois - 1], annee)
            )
            c1, c2 = st.columns(2)
            if c1.button("Oui, tout supprimer", key="btn_reset_confirm_{}".format(cle_mois)):
                with get_session() as session:
                    nb = reinitialiser_mois(session, annee, mois)
                # Vide le cache Streamlit (état du data_editor) pour ce mois, sinon
                # la grille éditable réaffiche les anciennes valeurs mises en cache
                # par son "key" au lieu des données fraîches (vidées) de la base.
                for cle in list(st.session_state.keys()):
                    if cle.startswith("editeur_planning_{}".format(cle_mois)):
                        del st.session_state[cle]
                st.session_state[cle_confirmation] = False
                st.success("{} créneau(x) supprimé(s) pour {} {}.".format(nb, MOIS_LABELS_FR[mois - 1], annee))
                st.rerun()
            if c2.button("Annuler", key="btn_reset_cancel_{}".format(cle_mois)):
                st.session_state[cle_confirmation] = False
                st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# 3. Chargement des données du mois
# ---------------------------------------------------------------------------

with get_session() as session:
    tous_medecins = session.query(Medecin).all()
    noms_par_id = {m.id: m.nom_complet() for m in tous_medecins}
    id_par_nom = {v: k for k, v in noms_par_id.items()}
    medecins_actifs = sorted(
        ((m.id, m.nom_complet()) for m in tous_medecins if m.actif), key=lambda t: t[1]
    )
    medecins_actifs_noms = [nom for _id, nom in medecins_actifs]

    affectations_db = (
        session.query(Affectation)
        .filter(Affectation.date >= jours[0], Affectation.date <= jours[-1])
        .all()
    )
    indispo_par_medecin = indisponibilites_par_medecin(
        session, [m for m in tous_medecins if m.actif], jours[0], jours[-1]
    )

affectations = [(a.date, a.poste_code, a.medecin_id) for a in affectations_db]
degradation_mois = any(a.degrade for a in affectations_db)

# ---------------------------------------------------------------------------
# 4. Indicateurs (KPIs)
# ---------------------------------------------------------------------------

kpis = grille.calculer_kpis(jours, affectations)
col1, col2, col3 = st.columns(3)
col1.metric("Taux de complétion du mois", "{} %".format(kpis["taux_completion"]))
col2.metric("Gardes de nuit générées", kpis["nb_gardes"])
col3.metric("Slots affectés / applicables", "{} / {}".format(kpis["nb_remplis"], kpis["nb_applicables"]))

if degradation_mois:
    st.error(
        "⚠️ Ce mois contient des affectations générées en **mode dégradé** "
        "(un ou plusieurs postes sacrifiés faute d'effectif à certaines dates)."
    )

# ---------------------------------------------------------------------------
# 5. Deux vues : par poste (avec édition) / par médecin (lecture seule)
# ---------------------------------------------------------------------------

onglet_poste, onglet_medecin = st.tabs(["Vue globale par Poste", "Vue individuelle par Médecin"])

with onglet_poste:
    df_grille = grille.construire_grille(jours, affectations, noms_par_id)

    st.subheader("Vue d'ensemble du mois")
    st.caption("Voir la légende des couleurs en haut de page. Gris = poste non applicable ce jour-là.")
    st.dataframe(grille.styliser_grille(df_grille), hide_index=True, use_container_width=True, height=600)

    st.subheader("Édition manuelle")
    st.caption(
        "Modifie directement une cellule via le menu déroulant, puis clique sur "
        "'Valider et enregistrer les modifications'. Une vérification rapide "
        "(pas de double affectation le même jour, pas de dépassement des 50h/semaine) "
        "est faite avant l'enregistrement."
    )

    noms_presents_non_actifs = {
        val
        for col in df_grille.columns
        if col != grille.COL_JOUR
        for val in df_grille[col]
        if val not in (grille.VIDE, grille.NON_APPLICABLE) and val not in medecins_actifs_noms
    }
    options_medecins = ["", grille.NON_APPLICABLE] + medecins_actifs_noms + sorted(noms_presents_non_actifs)

    column_config = {
        grille.COL_JOUR: st.column_config.TextColumn(disabled=True),
    }
    for _code, _slot, colonne_label in grille.COLONNES_GRILLE:
        column_config[colonne_label] = st.column_config.SelectboxColumn(
            options=options_medecins,
            required=False,
        )

    df_edite = st.data_editor(
        df_grille,
        column_config=column_config,
        hide_index=True,
        use_container_width=True,
        num_rows="fixed",  # pas d'ajout/suppression de ligne : la structure des jours est fixe
        height=700,
        key="editeur_planning_{}".format(cle_mois),
    )

    if st.button("Valider et enregistrer les modifications", type="primary"):
        affectations_editees = grille.extraire_affectations_editees(df_edite, jours, id_par_nom)
        erreurs = valider_grille_manuelle(affectations_editees, noms_par_id)

        if erreurs:
            st.error(
                "Impossible d'enregistrer, les problèmes suivants doivent être corrigés "
                "d'abord :\n\n" + "\n".join("- {}".format(e) for e in erreurs)
            )
        else:
            with get_session() as session:
                session.query(Affectation).filter(
                    Affectation.date >= jours[0], Affectation.date <= jours[-1]
                ).delete(synchronize_session=False)
                for date, poste_code, medecin_id in affectations_editees:
                    if medecin_id is None:
                        continue
                    session.add(
                        Affectation(
                            date=date,
                            poste_code=poste_code,
                            medecin_id=medecin_id,
                            statut=StatutAffectation.MODIFIE_MANUELLEMENT.value,
                            degrade=False,
                        )
                    )
            st.success("Modifications enregistrées.")
            st.rerun()

with onglet_medecin:
    st.subheader("Planning individuel par médecin")
    st.caption(
        "Lecture seule — pour modifier une affectation, passe par l'onglet "
        "'Vue globale par Poste'. Violet = congé/indisponibilité déclarée."
    )
    if not medecins_actifs:
        st.warning("Aucun médecin actif. Ajoute des médecins depuis la page 'Médecins & Cohortes'.")
    else:
        df_medecin = grille.construire_grille_par_medecin(jours, affectations, medecins_actifs, indispo_par_medecin)
        st.dataframe(
            grille.styliser_grille_par_medecin(df_medecin),
            hide_index=True,
            use_container_width=True,
            height=700,
        )
