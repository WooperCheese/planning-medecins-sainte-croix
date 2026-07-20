"""
Cette page a été fusionnée dans la page "Planning" : génération, vue colorée
et édition manuelle sont maintenant réunies au même endroit. Fichier conservé
sur disque (non supprimable automatiquement) mais volontairement RETIRÉ de la
liste de pages passée à st.navigation() dans streamlit_app.py : il n'apparaît
donc plus nulle part dans l'application, ce fichier n'est jamais exécuté.

100% compatible Python 3.9.
"""

from __future__ import annotations

import streamlit as st

from app.ui.common import afficher_sidebar_utilisateur, injecter_theme, require_login

injecter_theme()
require_login(["admin"])
afficher_sidebar_utilisateur()

st.title("Génération")
st.info(
    "Cette page a été fusionnée avec la page **Planning** (menu de gauche) : "
    "tu y trouveras le bouton de génération, la vue colorée du planning et "
    "l'édition manuelle, au même endroit."
)
