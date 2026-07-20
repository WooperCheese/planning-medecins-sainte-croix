"""
Page admin "Utilisateurs" : vue d'ensemble et gestion de tous les comptes de
connexion (admin/medecin/rh) — création générique, activation/désactivation,
régénération de mot de passe, suppression définitive.

Distincte de pages/1_Medecins_et_Cohortes.py (qui garde la création/régén.
de compte médecin depuis la fiche du médecin, cas d'usage le plus fréquent) :
cette page couvre la vue globale et les rôles admin/rh, qui n'ont pas de
fiche dédiée.

Cf. docs/superpowers/specs/2026-07-20-gestion-comptes-design.md.

100% compatible Python 3.9 : Optional[...] partout, jamais de `X | None`.
"""

from __future__ import annotations

import streamlit as st

from app.auth.comptes import IdentifiantDejaUtilise, creer_compte, regenerer_mot_de_passe, supprimer_compte
from app.db.models import Medecin, Role, User
from app.db.session import get_session
from app.ui.common import afficher_sidebar_utilisateur, injecter_css_bouton_danger, injecter_theme, require_login

injecter_theme()
utilisateur_courant = require_login(["admin"])
afficher_sidebar_utilisateur()

st.title("Utilisateurs")


@st.dialog("Nouveau compte")
def dialog_nouveau_compte(medecins_sans_compte: dict) -> None:
    username = st.text_input("Identifiant")
    role = st.selectbox("Rôle", [r.value for r in Role])
    medecin_id = None
    if role == Role.MEDECIN.value:
        if not medecins_sans_compte:
            st.info("Tous les médecins actifs ont déjà un compte.")
        else:
            medecin_label = st.selectbox("Médecin lié", list(medecins_sans_compte.keys()))
            medecin_id = medecins_sans_compte.get(medecin_label)

    if st.button("Créer le compte", type="primary"):
        if not username:
            st.error("L'identifiant est obligatoire.")
        elif role == Role.MEDECIN.value and medecin_id is None:
            st.error("Sélectionne un médecin à lier à ce compte.")
        else:
            try:
                with get_session() as session:
                    mot_de_passe = creer_compte(session, username, role, medecin_id)
            except IdentifiantDejaUtilise as erreur:
                st.error(str(erreur))
            else:
                st.success(
                    "Compte créé. Transmets ces identifiants à la personne concernée — le mot "
                    "de passe ne sera plus jamais affiché après avoir quitté cette fenêtre :"
                )
                st.code("Identifiant : {}\nMot de passe : {}".format(username, mot_de_passe))


@st.dialog("Régénérer le mot de passe")
def dialog_regenerer(user: User, nom_affiche: str) -> None:
    st.write("Compte **{}**.".format(nom_affiche))
    st.warning("L'ancien mot de passe cessera immédiatement de fonctionner.")
    if st.button("Régénérer", type="primary"):
        with get_session() as session:
            mot_de_passe = regenerer_mot_de_passe(session, user.id)
        st.success(
            "Nouveau mot de passe généré. Transmets-le à la personne concernée — il ne sera "
            "plus jamais affiché après avoir quitté cette fenêtre :"
        )
        st.code("Identifiant : {}\nMot de passe : {}".format(user.username, mot_de_passe))


@st.dialog("Supprimer le compte")
def dialog_supprimer(user: User, nom_affiche: str) -> None:
    st.warning(
        "Tu es sur le point de supprimer définitivement le compte **{}**. "
        "Cette action est irréversible.".format(nom_affiche)
    )
    confirmation = st.checkbox("Je confirme vouloir supprimer ce compte.")
    with st.container(key="confirmer_suppression"):
        injecter_css_bouton_danger("confirmer_suppression")
        if st.button("Confirmer la suppression", disabled=not confirmation):
            with get_session() as session:
                supprimer_compte(session, user.id)
            st.rerun()


with get_session() as session:
    tous_users = session.query(User).order_by(User.role, User.username).all()
    tous_medecins = {m.id: m for m in session.query(Medecin).all()}
    medecins_avec_compte = {u.medecin_id for u in tous_users if u.medecin_id is not None}
    medecins_sans_compte = {
        m.nom_complet(): m.id for m in tous_medecins.values() if m.actif and m.id not in medecins_avec_compte
    }

if st.button("+ Nouveau compte"):
    dialog_nouveau_compte(medecins_sans_compte)

st.divider()

with get_session() as session:
    tous_users = session.query(User).order_by(User.role, User.username).all()
    tous_medecins = {m.id: m for m in session.query(Medecin).all()}

    for u in tous_users:
        medecin_lie = tous_medecins.get(u.medecin_id) if u.medecin_id else None
        nom_affiche = "{} ({})".format(u.username, medecin_lie.nom_complet()) if medecin_lie else u.username

        cols = st.columns([3, 2, 3, 2, 2, 2, 2])
        cols[0].write("**{}**".format(u.username))
        cols[1].write(u.role)
        cols[2].write(medecin_lie.nom_complet() if medecin_lie else "—")
        cols[3].write("Actif" if u.actif else "Inactif")

        est_soi_meme = u.id == utilisateur_courant["id"]

        if not est_soi_meme:
            if cols[4].button("Désactiver" if u.actif else "Réactiver", key="toggle_user_{}".format(u.id)):
                with get_session() as s2:
                    user_db = s2.get(User, u.id)
                    user_db.actif = not user_db.actif
                st.rerun()

        if cols[5].button("Régén. mdp", key="regen_user_{}".format(u.id)):
            dialog_regenerer(u, nom_affiche)

        if not est_soi_meme:
            if cols[6].button("Supprimer", key="suppr_user_{}".format(u.id)):
                dialog_supprimer(u, nom_affiche)
