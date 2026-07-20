"""
Point d'entrée de l'application. Lancer avec :

    streamlit run streamlit_app.py

Avant le tout premier lancement, initialiser la base et créer le compte admin :

    python -m app.db.seed

Navigation : la liste des pages visibles dans la barre latérale est définie
explicitement ci-dessous via st.navigation(). C'est volontaire : ça permet de
retirer une page du menu (ex : l'ancienne page "Génération", fusionnée dans
"Planning") sans avoir à supprimer son fichier de pages/ — utile car les
fichiers du dossier utilisateur ne peuvent pas être supprimés par l'agent qui
maintient cette appli. pages/3_Generation.py existe donc toujours sur disque
mais n'apparaît plus nulle part : st.navigation() remplace entièrement la
détection automatique du dossier pages/.

IMPORTANT : st.navigation(...) doit être appelé AVANT tout st.stop() éventuel
(y compris celui de l'écran de connexion), sinon Streamlit retombe sur son
menu automatique (détection du dossier pages/, avec "Generation" inclus et
des titres sans accents) pour ce run-là. Seul .run() est retardé jusqu'après
la vérification de connexion — construire l'objet navigation suffit à
remplacer le menu automatique, l'exécuter est une étape séparée.
"""

import streamlit as st

from app.db.session import init_db
from app.ui.common import afficher_login, afficher_sidebar_utilisateur, configurer_page

configurer_page("Planning Médecins — Sainte-Croix")

try:
    init_db()
except Exception as erreur:
    st.error(
        "Impossible de se connecter à la base de données. Vérifie la configuration "
        "(secret DATABASE_URL dans les paramètres de l'app sur Streamlit Community "
        "Cloud, ou variable d'environnement DATABASE_URL en local) — voir "
        "docs/DEPLOIEMENT.md.\n\nDétail technique : {}".format(erreur)
    )
    st.stop()


def page_accueil() -> None:
    st.title("Planning Médecins Assistants — Sainte-Croix")
    st.write("Utilise le menu à gauche pour naviguer : Médecins & Cohortes, Congés, Planning.")
    if st.session_state["user"]["role"] != "admin":
        st.info(
            "Seul le rôle admin dispose d'une interface pour l'instant (V1). "
            "Les portails médecin et RH arrivent en V2."
        )


pg_accueil = st.Page(page_accueil, title="Accueil", icon="🏠", default=True)
pg_medecins = st.Page("pages/1_Medecins_et_Cohortes.py", title="Médecins & Cohortes", icon="🩺")
pg_conges = st.Page("pages/2_Conges.py", title="Congés", icon="🗓️")
pg_planning = st.Page("pages/4_Planning.py", title="Planning", icon="📋")

# Déclaré AVANT le contrôle de connexion, cf. note ci-dessus : c'est cet appel
# (et non .run()) qui supprime le menu automatique de Streamlit.
navigation = st.navigation([pg_accueil, pg_medecins, pg_conges, pg_planning])

if "user" not in st.session_state:
    afficher_login()
    st.stop()

afficher_sidebar_utilisateur()
navigation.run()
