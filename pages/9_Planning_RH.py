"""
Page RH : consultation du planning de toute l'équipe (lecture seule).

Copie du pattern de pages/5_Mon_Planning.py (portail médecin) — même
composant de grille, seul le rôle requis change. Cf.
docs/superpowers/specs/2026-07-21-portail-rh-design.md.

100% compatible Python 3.9 : Optional[...] partout, jamais de `X | None`.
"""

from __future__ import annotations

import datetime

import streamlit as st

from app.db.models import Affectation, Medecin
from app.db.session import get_session
from app.solver.engine import jours_du_mois
from app.solver.history import indisponibilites_par_medecin
from app.ui import planning_grid as grille
from app.ui.common import afficher_sidebar_utilisateur, injecter_theme, require_login

MOIS_LABELS_FR = [
    "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
]

injecter_theme()
user = require_login(["rh"])
afficher_sidebar_utilisateur()

st.title("Planning de l'équipe")
st.caption("Lecture seule.")

col_mois, col_annee = st.columns([2, 1])
aujourd_hui = datetime.date.today()
mois = col_mois.selectbox("Mois", list(range(1, 13)), index=aujourd_hui.month - 1, format_func=lambda m: MOIS_LABELS_FR[m - 1])
annee = col_annee.number_input("Année", min_value=2020, max_value=2100, value=aujourd_hui.year, step=1)

jours = jours_du_mois(annee, mois)

with get_session() as session:
    tous_medecins = session.query(Medecin).all()
    medecins_actifs = sorted(
        ((m.id, m.nom_complet()) for m in tous_medecins if m.actif), key=lambda t: t[1]
    )
    affectations_db = (
        session.query(Affectation)
        .filter(Affectation.date >= jours[0], Affectation.date <= jours[-1])
        .all()
    )
    indispo_par_medecin = indisponibilites_par_medecin(
        session, [m for m in tous_medecins if m.actif], jours[0], jours[-1]
    )

affectations = [(a.date, a.poste_code, a.medecin_id) for a in affectations_db]

if not medecins_actifs:
    st.warning("Aucun médecin actif pour l'instant.")
else:
    df_medecin = grille.construire_grille_par_medecin(jours, affectations, medecins_actifs, indispo_par_medecin)
    st.dataframe(
        grille.styliser_grille_par_medecin(df_medecin),
        hide_index=True,
        use_container_width=True,
        height=700,
    )

st.divider()
st.markdown(grille.construire_legende_html(), unsafe_allow_html=True)
