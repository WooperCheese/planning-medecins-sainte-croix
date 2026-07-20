"""
Point d'entrée de l'application. Lancer avec :

    streamlit run streamlit_app.py

Avant le tout premier lancement, initialiser la base et créer le compte admin :

    python -m app.db.seed

Navigation : la liste des pages visibles dans la barre latérale est définie
explicitement ci-dessous via st.navigation(), et dépend du RÔLE de
l'utilisateur connecté (admin voit les pages de gestion, medecin voit son
propre portail). C'est volontaire : ça permet aussi de retirer une page du
menu (ex : l'ancienne page "Génération", fusionnée dans "Planning") sans
avoir à supprimer son fichier de pages/ — utile car les fichiers du dossier
utilisateur ne peuvent pas être supprimés par l'agent qui maintient cette
appli. pages/3_Generation.py existe donc toujours sur disque mais n'apparaît
plus nulle part : st.navigation() remplace entièrement la détection
automatique du dossier pages/.

IMPORTANT : st.navigation(...) doit être appelé AVANT tout st.stop() éventuel
(y compris celui de l'écran de connexion), sinon Streamlit retombe sur son
menu automatique (détection du dossier pages/, avec "Generation" inclus et
des titres sans accents) pour ce run-là. Seul .run() est retardé jusqu'après
la vérification de connexion — construire l'objet navigation suffit à
remplacer le menu automatique, l'exécuter est une étape séparée. Tant que le
rôle n'est pas encore connu (personne connecté), le menu par défaut (admin)
est utilisé pour l'écran de connexion — sans conséquence puisque chaque page
revérifie elle-même le rôle via require_login().
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
    role = st.session_state["user"]["role"]
    if role == "medecin":
        st.write("Utilise le menu à gauche : 'Mon Planning' pour consulter le planning de l'équipe, "
                  "'Mes Congés & Heures' pour déclarer tes indisponibilités et heures supplémentaires.")
    elif role == "admin":
        st.write("Utilise le menu à gauche pour naviguer : Médecins & Cohortes, Congés, Planning.")
    elif role == "rh":
        st.write("Utilise le menu à gauche : 'Planning' pour consulter le planning de l'équipe, "
                  "'Export Paie' pour télécharger les heures du mois au format Excel.")
    else:
        st.info("Aucune interface disponible pour le rôle '{}' pour l'instant.".format(role))


pg_accueil = st.Page(page_accueil, title="Accueil", icon="🏠", default=True)

utilisateur_session = st.session_state.get("user")
role_courant = utilisateur_session["role"] if utilisateur_session else None

pg_mon_compte = st.Page("pages/7_Mon_Compte.py", title="Mon Compte", icon="🔑")

if role_courant == "medecin":
    pg_mon_planning = st.Page("pages/5_Mon_Planning.py", title="Mon Planning", icon="📋")
    pg_mes_conges = st.Page("pages/6_Mes_Conges_Et_Heures.py", title="Mes Congés & Heures", icon="🗓️")
    pages = [pg_accueil, pg_mon_planning, pg_mes_conges, pg_mon_compte]
elif role_courant == "rh":
    pg_planning_rh = st.Page("pages/9_Planning_RH.py", title="Planning", icon="📋")
    pg_export_paie = st.Page("pages/10_Export_Paie.py", title="Export Paie", icon="💰")
    pages = [pg_accueil, pg_planning_rh, pg_export_paie, pg_mon_compte]
else:
    # Défaut (rôle admin, ou personne connecté pour l'instant) : pages de gestion.
    pg_medecins = st.Page("pages/1_Medecins_et_Cohortes.py", title="Médecins & Cohortes", icon="🩺")
    pg_conges = st.Page("pages/2_Conges.py", title="Congés", icon="🗓️")
    pg_planning = st.Page("pages/4_Planning.py", title="Planning", icon="📋")
    pg_utilisateurs = st.Page("pages/8_Utilisateurs.py", title="Utilisateurs", icon="👥")
    pages = [pg_accueil, pg_medecins, pg_conges, pg_planning, pg_utilisateurs, pg_mon_compte]

# Déclaré AVANT le contrôle de connexion, cf. note ci-dessus : c'est cet appel
# (et non .run()) qui supprime le menu automatique de Streamlit.
navigation = st.navigation(pages)

if "user" not in st.session_state:
    afficher_login()
    st.stop()

afficher_sidebar_utilisateur()
navigation.run()
