"""
100% compatible Python 3.9 : Optional[...] partout, jamais de `X | None`.
"""

from __future__ import annotations

import datetime

import streamlit as st

from app.auth.comptes import IdentifiantDejaUtilise, creer_compte_medecin, regenerer_mot_de_passe
from app.db.models import Cohorte, Medecin, Role, User
from app.db.session import get_session
from app.ui.common import afficher_sidebar_utilisateur, injecter_theme, require_login

injecter_theme()
require_login(["admin"])
afficher_sidebar_utilisateur()

st.title("Médecins & Cohortes")


@st.dialog("Nouvelle cohorte")
def dialog_nouvelle_cohorte() -> None:
    label = st.text_input("Label (ex : Nov 2025 – Mai 2026)")
    date_debut = st.date_input("Date de début", value=datetime.date.today())
    date_fin = st.date_input("Date de fin", value=datetime.date.today() + datetime.timedelta(days=180))
    if st.button("Créer la cohorte", type="primary"):
        if not label:
            st.error("Le label est obligatoire.")
        else:
            with get_session() as session:
                session.add(Cohorte(label=label, date_debut=date_debut, date_fin=date_fin, archivee=False))
            st.rerun()


@st.dialog("Nouveau médecin")
def dialog_nouveau_medecin(cohorte_options: dict) -> None:
    nom = st.text_input("Nom")
    prenom = st.text_input("Prénom")
    cohorte_label = st.selectbox("Cohorte", list(cohorte_options.keys()))
    date_arrivee = st.date_input("Date d'arrivée dans le service", value=datetime.date.today())
    date_depart = st.date_input("Date de départ (optionnel)", value=None)
    if st.button("Ajouter le médecin", type="primary"):
        if not nom or not prenom:
            st.error("Nom et prénom sont obligatoires.")
        else:
            with get_session() as session:
                session.add(
                    Medecin(
                        nom=nom,
                        prenom=prenom,
                        cohorte_id=cohorte_options[cohorte_label],
                        actif=True,
                        date_arrivee=date_arrivee,
                        date_depart=date_depart,
                    )
                )
            st.rerun()


def _suggestion_identifiant(medecin: Medecin) -> str:
    return "{}.{}".format(medecin.prenom, medecin.nom).lower().replace(" ", "")


@st.dialog("Créer un accès de connexion")
def dialog_creer_compte(medecin: Medecin) -> None:
    st.write("Compte pour **{}** (rôle médecin).".format(medecin.nom_complet()))
    username = st.text_input("Identifiant", value=_suggestion_identifiant(medecin))
    if st.button("Créer l'accès", type="primary"):
        if not username:
            st.error("L'identifiant est obligatoire.")
        else:
            try:
                with get_session() as session:
                    mot_de_passe = creer_compte_medecin(session, medecin.id, username)
            except IdentifiantDejaUtilise as erreur:
                st.error(str(erreur))
            else:
                st.success(
                    "Compte créé. Transmets ces identifiants à {} — le mot de passe ne "
                    "sera plus jamais affiché après avoir quitté cette fenêtre :".format(
                        medecin.nom_complet()
                    )
                )
                st.code("Identifiant : {}\nMot de passe : {}".format(username, mot_de_passe))


@st.dialog("Régénérer le mot de passe")
def dialog_regenerer_compte(medecin: Medecin, user: User) -> None:
    st.write("Compte **{}** de **{}**.".format(user.username, medecin.nom_complet()))
    st.warning("L'ancien mot de passe cessera immédiatement de fonctionner.")
    if st.button("Régénérer", type="primary"):
        with get_session() as session:
            mot_de_passe = regenerer_mot_de_passe(session, user.id)
        st.success(
            "Nouveau mot de passe généré. Transmets-le à {} — il ne sera plus jamais "
            "affiché après avoir quitté cette fenêtre :".format(medecin.nom_complet())
        )
        st.code("Identifiant : {}\nMot de passe : {}".format(user.username, mot_de_passe))


st.header("Cohortes")
if st.button("+ Nouvelle cohorte"):
    dialog_nouvelle_cohorte()

with get_session() as session:
    cohortes = session.query(Cohorte).order_by(Cohorte.date_debut.desc()).all()
    for c in cohortes:
        cols = st.columns([3, 2, 2, 2])
        cols[0].write("**{}**".format(c.label))
        cols[1].write("{} → {}".format(c.date_debut, c.date_fin))
        cols[2].write("Archivée" if c.archivee else "Active")
        if cols[3].button("Archiver" if not c.archivee else "Désarchiver", key="arch_{}".format(c.id)):
            with get_session() as s2:
                cohorte_db = s2.get(Cohorte, c.id)
                cohorte_db.archivee = not cohorte_db.archivee
            st.rerun()

st.divider()
st.header("Médecins assistants")

with get_session() as session:
    cohortes_actives = session.query(Cohorte).filter(Cohorte.archivee.is_(False)).all()
    cohorte_options = {c.label: c.id for c in cohortes_actives}

if not cohorte_options:
    st.warning("Crée d'abord au moins une cohorte active avant d'ajouter des médecins.")
elif st.button("+ Nouveau médecin"):
    dialog_nouveau_medecin(cohorte_options)

with get_session() as session:
    medecins = session.query(Medecin).order_by(Medecin.actif.desc(), Medecin.nom).all()
    comptes_par_medecin = {
        u.medecin_id: u for u in session.query(User).filter(User.role == Role.MEDECIN.value).all()
    }
    for m in medecins:
        cols = st.columns([3, 2, 2, 2, 2, 2])
        cols[0].write(m.nom_complet())
        cols[1].write(m.cohorte.label if m.cohorte else "-")
        cols[2].write("{} → {}".format(m.date_arrivee, m.date_depart or "..."))
        cols[3].write("Actif" if m.actif else "Inactif")
        if cols[4].button("Désactiver" if m.actif else "Réactiver", key="toggle_{}".format(m.id)):
            with get_session() as s2:
                medecin_db = s2.get(Medecin, m.id)
                medecin_db.actif = not medecin_db.actif
            st.rerun()

        compte = comptes_par_medecin.get(m.id)
        if compte is None:
            if cols[5].button("+ Créer accès", key="creer_compte_{}".format(m.id)):
                dialog_creer_compte(m)
        else:
            if cols[5].button("Régén. mot de passe", key="regen_compte_{}".format(m.id)):
                dialog_regenerer_compte(m, compte)
