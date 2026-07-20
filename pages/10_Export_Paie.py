"""
Page RH : export Excel des heures (prévues + supplémentaires) pour la paie.

Total par médecin sur le mois choisi, pas de détail ligne par ligne (cf.
docs/superpowers/specs/2026-07-21-portail-rh-design.md).

100% compatible Python 3.9 : Optional[...] partout, jamais de `X | None`.
"""

from __future__ import annotations

import datetime

import pandas as pd
import streamlit as st

from app.db.models import Medecin
from app.db.session import get_session
from app.rh.paie import generer_export_excel, heures_prevues_par_medecin, heures_sup_par_medecin
from app.solver.engine import jours_du_mois
from app.ui.common import afficher_sidebar_utilisateur, injecter_theme, require_login

MOIS_LABELS_FR = [
    "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
]

injecter_theme()
require_login(["rh"])
afficher_sidebar_utilisateur()

st.title("Export Paie")
st.caption("Total des heures prévues (planning) et des heures supplémentaires déclarées, par médecin.")

col_mois, col_annee = st.columns([2, 1])
aujourd_hui = datetime.date.today()
mois = col_mois.selectbox("Mois", list(range(1, 13)), index=aujourd_hui.month - 1, format_func=lambda m: MOIS_LABELS_FR[m - 1])
annee = col_annee.number_input("Année", min_value=2020, max_value=2100, value=aujourd_hui.year, step=1)

jours = jours_du_mois(annee, mois)

with get_session() as session:
    medecins_actifs = session.query(Medecin).filter(Medecin.actif.is_(True)).all()
    heures_prevues = heures_prevues_par_medecin(session, medecins_actifs, jours[0], jours[-1])
    heures_sup = heures_sup_par_medecin(session, medecins_actifs, jours[0], jours[-1])
    noms_medecins = {m.id: m.nom_complet() for m in medecins_actifs}

if not medecins_actifs:
    st.warning("Aucun médecin actif pour l'instant.")
else:
    lignes = [
        {
            "Médecin": noms_medecins[m.id],
            "Heures prévues": heures_prevues.get(m.id, 0.0),
            "Heures sup": heures_sup.get(m.id, 0.0),
            "Total": heures_prevues.get(m.id, 0.0) + heures_sup.get(m.id, 0.0),
        }
        for m in sorted(medecins_actifs, key=lambda m: m.nom_complet())
    ]
    df = pd.DataFrame(lignes)
    st.dataframe(df, hide_index=True, use_container_width=True)

    export_bytes = generer_export_excel(medecins_actifs, heures_prevues, heures_sup)
    st.download_button(
        "Télécharger l'export Excel",
        data=export_bytes,
        file_name="paie_{}_{:02d}.xlsx".format(annee, mois),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )
