"""
Page médecin : déclaration de ses propres congés/indisponibilités (avec
validation admin, cf. StatutIndisponibilite) et de ses heures supplémentaires
(simple journal, sans validation).

100% compatible Python 3.9 : Optional[...] partout, jamais de `X | None`.
"""

from __future__ import annotations

import datetime

import streamlit as st

from app.db.models import HeureSup, Indisponibilite, StatutIndisponibilite, TypeIndisponibilite
from app.db.session import get_session
from app.ui.common import afficher_sidebar_utilisateur, injecter_theme, require_login

injecter_theme()
user = require_login(["medecin"])
afficher_sidebar_utilisateur()

st.title("Mes congés & heures supplémentaires")

medecin_id = user["medecin_id"]
if medecin_id is None:
    st.error(
        "Ce compte n'est lié à aucune fiche médecin. Contacte l'admin pour "
        "corriger la configuration de ton compte."
    )
    st.stop()

STATUT_LABELS = {
    StatutIndisponibilite.EN_ATTENTE.value: "⏳ En attente",
    StatutIndisponibilite.VALIDEE.value: "✅ Validé",
    StatutIndisponibilite.REFUSEE.value: "❌ Refusé",
}

onglet_conges, onglet_heures = st.tabs(["Mes congés", "Mes heures sup"])

with onglet_conges:
    st.subheader("Déclarer une indisponibilité")
    st.caption("Ta demande sera examinée par l'admin avant de compter dans le planning.")

    with st.form("nouvelle_indispo_medecin"):
        col1, col2 = st.columns(2)
        date_debut = col1.date_input("Du", value=datetime.date.today())
        date_fin = col2.date_input("Au", value=datetime.date.today())
        type_indispo = st.selectbox("Type", [t.value for t in TypeIndisponibilite])
        commentaire = st.text_input("Commentaire (optionnel)")
        submit = st.form_submit_button("Envoyer la demande", type="primary")

    if submit:
        if date_fin < date_debut:
            st.error("La date de fin doit être postérieure ou égale à la date de début.")
        else:
            with get_session() as session:
                session.add(
                    Indisponibilite(
                        medecin_id=medecin_id,
                        date_debut=date_debut,
                        date_fin=date_fin,
                        type=type_indispo,
                        commentaire=commentaire or None,
                        statut=StatutIndisponibilite.EN_ATTENTE.value,
                    )
                )
            st.success("Demande envoyée, en attente de validation par l'admin.")
            st.rerun()

    st.divider()
    st.subheader("Mes déclarations")

    with get_session() as session:
        mes_indispos = (
            session.query(Indisponibilite)
            .filter(Indisponibilite.medecin_id == medecin_id)
            .order_by(Indisponibilite.date_debut.desc())
            .all()
        )
        if not mes_indispos:
            st.write("Aucune déclaration pour l'instant.")
        for i in mes_indispos:
            cols = st.columns([2, 2, 2, 3, 2])
            cols[0].write(str(i.date_debut))
            cols[1].write(str(i.date_fin))
            cols[2].write(i.type)
            cols[3].write(i.commentaire or "")
            cols[4].write(STATUT_LABELS.get(i.statut, i.statut))

with onglet_heures:
    st.subheader("Déclarer des heures supplémentaires")

    with st.form("nouvelle_heure_sup"):
        date_heure = st.date_input("Date", value=datetime.date.today())
        nb_heures = st.number_input("Nombre d'heures", min_value=0.0, step=0.5)
        motif = st.text_area("Motif")
        submit_heure = st.form_submit_button("Enregistrer", type="primary")

    if submit_heure:
        if nb_heures <= 0:
            st.error("Le nombre d'heures doit être supérieur à 0.")
        elif not motif:
            st.error("Le motif est obligatoire.")
        else:
            with get_session() as session:
                session.add(
                    HeureSup(
                        medecin_id=medecin_id,
                        date=date_heure,
                        nb_heures=nb_heures,
                        motif=motif,
                    )
                )
            st.success("Heures supplémentaires enregistrées.")
            st.rerun()

    st.divider()
    st.subheader("Mes déclarations")

    with get_session() as session:
        mes_heures = (
            session.query(HeureSup)
            .filter(HeureSup.medecin_id == medecin_id)
            .order_by(HeureSup.date.desc())
            .all()
        )
        if not mes_heures:
            st.write("Aucune déclaration pour l'instant.")
        for h in mes_heures:
            cols = st.columns([2, 2, 5])
            cols[0].write(str(h.date))
            cols[1].write("{} h".format(h.nb_heures))
            cols[2].write(h.motif)
