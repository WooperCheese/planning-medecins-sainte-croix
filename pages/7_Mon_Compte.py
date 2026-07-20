"""
Page "Mon Compte" : changement de mot de passe en self-service, visible par
tous les rôles connectés (admin, medecin, à terme rh).

Redemande l'ancien mot de passe avant d'accepter le nouveau (protection si
une session reste ouverte sur un poste partagé — cas réel en milieu
hospitalier). Cf. docs/superpowers/specs/2026-07-20-gestion-comptes-design.md.

100% compatible Python 3.9 : Optional[...] partout, jamais de `X | None`.
"""

from __future__ import annotations

import streamlit as st

from app.auth.comptes import AncienMotDePasseIncorrect, changer_propre_mot_de_passe
from app.db.session import get_session
from app.ui.common import afficher_sidebar_utilisateur, injecter_theme, require_login

LONGUEUR_MIN_MOT_DE_PASSE = 8

injecter_theme()
user = require_login()
afficher_sidebar_utilisateur()

st.title("Mon compte")
st.caption("Connecté en tant que **{}** ({}).".format(user["username"], user["role"]))

st.subheader("Changer mon mot de passe")

with st.form("changer_mot_de_passe"):
    ancien = st.text_input("Mot de passe actuel", type="password")
    nouveau = st.text_input("Nouveau mot de passe", type="password")
    confirmation = st.text_input("Confirmer le nouveau mot de passe", type="password")
    submit = st.form_submit_button("Changer le mot de passe", type="primary")

if submit:
    if len(nouveau) < LONGUEUR_MIN_MOT_DE_PASSE:
        st.error("Le nouveau mot de passe doit contenir au moins {} caractères.".format(LONGUEUR_MIN_MOT_DE_PASSE))
    elif nouveau != confirmation:
        st.error("Le nouveau mot de passe et sa confirmation ne correspondent pas.")
    else:
        try:
            with get_session() as session:
                changer_propre_mot_de_passe(session, user["id"], ancien, nouveau)
        except AncienMotDePasseIncorrect:
            st.error("Le mot de passe actuel saisi est incorrect.")
        else:
            st.success("Mot de passe changé avec succès.")
