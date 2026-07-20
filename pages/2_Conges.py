"""
100% compatible Python 3.9 : Optional[...] partout, jamais de `X | None`.
"""

from __future__ import annotations

import datetime

import streamlit as st

from app.db.models import Indisponibilite, Medecin, TypeIndisponibilite
from app.db.session import get_session
from app.ui.common import afficher_sidebar_utilisateur, injecter_theme, require_login

injecter_theme()
require_login(["admin"])
afficher_sidebar_utilisateur()

st.title("Congés & indisponibilités")

with get_session() as session:
    medecins = session.query(Medecin).filter(Medecin.actif.is_(True)).order_by(Medecin.nom).all()
    options = {m.nom_complet(): m.id for m in medecins}


@st.dialog("Nouvelle indisponibilité")
def dialog_nouvelle_indispo(options: dict) -> None:
    medecin_label = st.selectbox("Médecin", list(options.keys()))
    col1, col2 = st.columns(2)
    date_debut = col1.date_input("Du", value=datetime.date.today())
    date_fin = col2.date_input("Au", value=datetime.date.today())
    type_indispo = st.selectbox("Type", [t.value for t in TypeIndisponibilite])
    commentaire = st.text_input("Commentaire (optionnel)")
    if st.button("Enregistrer", type="primary"):
        if date_fin < date_debut:
            st.error("La date de fin doit être postérieure ou égale à la date de début.")
        else:
            with get_session() as session:
                session.add(
                    Indisponibilite(
                        medecin_id=options[medecin_label],
                        date_debut=date_debut,
                        date_fin=date_fin,
                        type=type_indispo,
                        commentaire=commentaire or None,
                    )
                )
            st.rerun()


if not options:
    st.warning("Aucun médecin actif. Ajoute des médecins depuis la page 'Médecins & Cohortes'.")
elif st.button("+ Nouvelle indisponibilité"):
    dialog_nouvelle_indispo(options)

st.divider()
st.subheader("Indisponibilités à venir ou en cours")

with get_session() as session:
    aujourdhui = datetime.date.today()
    indispos = (
        session.query(Indisponibilite)
        .join(Medecin)
        .filter(Indisponibilite.date_fin >= aujourdhui)
        .order_by(Indisponibilite.date_debut)
        .all()
    )
    for i in indispos:
        cols = st.columns([3, 2, 2, 3, 1])
        cols[0].write(i.medecin.nom_complet())
        cols[1].write(str(i.date_debut))
        cols[2].write(str(i.date_fin))
        cols[3].write(i.type + (" — {}".format(i.commentaire) if i.commentaire else ""))
        if cols[4].button("Suppr.", key="del_{}".format(i.id)):
            with get_session() as s2:
                obj = s2.get(Indisponibilite, i.id)
                s2.delete(obj)
            st.rerun()
