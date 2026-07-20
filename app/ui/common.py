"""
Helpers partagés par toutes les pages Streamlit : configuration de page /
thème visuel, login, garde d'accès par rôle, affichage de la barre latérale
utilisateur.

100% compatible Python 3.9 : Optional[...] partout, jamais de `X | None`.
"""

from __future__ import annotations

from typing import Optional

import streamlit as st

from app.auth.auth import authenticate

# ---------------------------------------------------------------------------
# Thème "clinique" : fond clair, texte bleu nuit très foncé, boutons bleu nuit
# à texte blanc. Toutes les couleurs de l'appli vivent ici, pas éparpillées
# page par page.
#
# Note importante : st.dataframe / st.data_editor sont rendus sur un canvas
# (glide-data-grid) qui suit le thème NATIF Streamlit (.streamlit/config.toml),
# pas ce CSS — ce fichier doit rester cohérent avec ce thème. En revanche,
# tous les autres widgets (boutons, sidebar, textes, métriques, popovers,
# dialogues) sont du HTML/CSS classique et DOIVENT être forcés ici avec
# !important, car le thème natif seul ne suffit pas à garantir le contraste
# si jamais .streamlit/config.toml n'est pas chargé (mauvais dossier de
# lancement, serveur pas redémarré, thème système qui prend le dessus, etc.).
# Chaque règle ci-dessous liste plusieurs sélecteurs équivalents pour rester
# robuste aux changements de markup internes entre versions de Streamlit.
# ---------------------------------------------------------------------------

COULEUR_FOND = "#f4f7f9"
# Sidebar bleu nuit foncé avec texte blanc (inversion volontaire par rapport à
# l'ancien fond clair) : cf. docs/superpowers/specs/2026-07-21-refonte-design-design.md.
# Contraste très élevé (fond très foncé + texte quasi blanc), plus sûr que
# l'ancien schéma clair/foncé côté accessibilité.
COULEUR_FOND_SIDEBAR = "#0F1F3D"
COULEUR_TEXTE = "#0F172A"  # bleu nuit très foncé, lisibilité maximale
COULEUR_ACCENT = "#0f6674"  # bleu canard doux (titres)
COULEUR_BOUTON_FOND = "#1E3A8A"  # bleu nuit
COULEUR_BOUTON_FOND_HOVER = "#152a63"
COULEUR_BOUTON_TEXTE = "#FFFFFF"
COULEUR_SIDEBAR_TEXTE = "#F8FAFC"  # quasi blanc, lisible sur le fond sidebar foncé
COULEUR_DANGER = "#dc2626"
COULEUR_DANGER_HOVER = "#b91c1c"

# Police Inter (Google Fonts) avec fallback système explicite : si
# fonts.googleapis.com est bloqué (réseau hospitalier restrictif, hors ligne),
# le navigateur retombe silencieusement sur -apple-system/BlinkMacSystemFont
# sans aucune casse visuelle.
POLICE_CSS = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"

THEME_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

/* --- Fond et texte général de l'application --- */
[data-testid="stAppViewContainer"], .stApp {{
    background-color: {fond};
    font-family: {police};
}}
[data-testid="stHeader"] {{
    background-color: transparent;
}}
.stApp, .stApp p, .stApp span, .stApp label, .stApp li,
.stMarkdown, .stMarkdown p, .stMarkdown li,
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] * {{
    color: {texte} !important;
    font-family: {police};
}}
h1, h2, h3, h4 {{
    color: {accent} !important;
    font-family: {police};
}}

/* --- Barre latérale : fond bleu nuit foncé + texte blanc --- */
section[data-testid="stSidebar"], [data-testid="stSidebar"] {{
    background-color: {fond_sidebar} !important;
    font-family: {police};
}}
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] li,
section[data-testid="stSidebar"] .stMarkdown,
[data-testid="stSidebarNav"] a,
[data-testid="stSidebarNav"] span,
[data-testid="stSidebarNavLink"],
[data-testid="stSidebarNavLink"] * {{
    color: {sidebar_texte} !important;
}}
[data-testid="stSidebarNavLink"][aria-current="page"] {{
    color: #ffffff !important;
    background-color: rgba(255, 255, 255, 0.12);
    border-radius: 6px;
    font-weight: 700;
}}

/* --- Boutons : TOUS les types (primary/secondary/tertiary), formulaires,
   popovers, dialogues. Fond bleu nuit, texte blanc pur, quel que soit le
   thème natif sous-jacent. Plusieurs sélecteurs pour couvrir les différentes
   versions du markup Streamlit. --- */
.stButton button,
.stFormSubmitButton button,
.stDownloadButton button,
.stLinkButton a,
[data-testid="stPopover"] button,
[data-testid="stDialog"] button,
button[kind="primary"],
button[kind="secondary"],
button[kind="tertiary"],
[data-testid^="stBaseButton-"],
[data-testid^="baseButton-"] {{
    background-color: {bouton_fond} !important;
    color: {bouton_texte} !important;
    border: 1px solid {bouton_fond} !important;
    font-family: {police};
}}
.stButton button:hover,
.stFormSubmitButton button:hover,
.stDownloadButton button:hover,
[data-testid="stPopover"] button:hover,
[data-testid="stDialog"] button:hover,
button[kind="primary"]:hover,
button[kind="secondary"]:hover,
[data-testid^="stBaseButton-"]:hover {{
    background-color: {bouton_fond_hover} !important;
    border-color: {bouton_fond_hover} !important;
    color: {bouton_texte} !important;
}}
.stButton button p, .stFormSubmitButton button p, [data-testid^="stBaseButton-"] p {{
    color: {bouton_texte} !important;
}}

/* --- Bouton(s) dans la sidebar (ex: "Se déconnecter") : le fond navy par
   défaut se fondrait dans le nouveau fond de sidebar, tout aussi foncé.
   Bordure teal + fond légèrement éclairci pour rester distinct. --- */
section[data-testid="stSidebar"] .stButton button {{
    background-color: rgba(255, 255, 255, 0.06) !important;
    border: 1px solid {accent} !important;
    color: #ffffff !important;
}}
section[data-testid="stSidebar"] .stButton button:hover {{
    background-color: {accent} !important;
    border-color: {accent} !important;
}}

/* --- Logo / monogramme sidebar --- */
.sc-logo-bloc {{
    display: flex;
    align-items: center;
    gap: 0.6rem;
    padding: 0.25rem 0 1.1rem 0;
}}
.sc-logo-monogramme {{
    width: 36px;
    height: 36px;
    border-radius: 8px;
    background-color: {accent};
    color: #ffffff;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    font-size: 0.85rem;
    font-family: {police};
    flex-shrink: 0;
}}
.sc-logo-nom {{
    color: #ffffff;
    font-weight: 600;
    font-size: 0.95rem;
    font-family: {police};
    line-height: 1.2;
}}

/* --- Cartes KPI (st.metric) --- */
[data-testid="stMetric"] {{
    background-color: #ffffff;
    border: 1px solid #dde5e9;
    border-radius: 10px;
    padding: 0.9rem 1rem;
}}
[data-testid="stMetricLabel"], [data-testid="stMetricLabel"] * {{
    color: {texte} !important;
}}
[data-testid="stMetricValue"], [data-testid="stMetricValue"] * {{
    color: {accent} !important;
}}
</style>
""".format(
    fond=COULEUR_FOND,
    fond_sidebar=COULEUR_FOND_SIDEBAR,
    texte=COULEUR_TEXTE,
    accent=COULEUR_ACCENT,
    sidebar_texte=COULEUR_SIDEBAR_TEXTE,
    bouton_fond=COULEUR_BOUTON_FOND,
    bouton_fond_hover=COULEUR_BOUTON_FOND_HOVER,
    bouton_texte=COULEUR_BOUTON_TEXTE,
    police=POLICE_CSS,
)


def injecter_theme() -> None:
    """Injecte le CSS du thème. Peut être appelé sur chaque page sans risque
    (contrairement à st.set_page_config, qui ne peut être appelé qu'une fois
    par exécution — cf. configurer_page, réservé au script d'entrée)."""
    st.markdown(THEME_CSS, unsafe_allow_html=True)


def configurer_page(titre: str) -> None:
    """À appeler en tout premier, avant tout autre appel st.*, UNIQUEMENT dans
    le script d'entrée (streamlit_app.py) : mode large + thème clinique.
    Les pages individuelles, elles, appellent seulement injecter_theme()."""
    st.set_page_config(page_title=titre, layout="wide")
    injecter_theme()


def injecter_css_bouton_danger(cle_container: str) -> None:
    """Colore en rouge (au lieu du bleu nuit par défaut) le(s) bouton(s)
    placés dans un st.container(key=cle_container). Streamlit n'a pas de
    type="danger" natif pour st.button ; on cible le conteneur via la classe
    CSS "st-key-<cle>" que Streamlit génère pour tout st.container(key=...)."""
    css = """
    <style>
    .st-key-{cle} button {{
        background-color: {danger} !important;
        border-color: {danger} !important;
        color: #ffffff !important;
    }}
    .st-key-{cle} button:hover {{
        background-color: {danger_hover} !important;
        border-color: {danger_hover} !important;
    }}
    </style>
    """.format(cle=cle_container, danger=COULEUR_DANGER, danger_hover=COULEUR_DANGER_HOVER)
    st.markdown(css, unsafe_allow_html=True)


def afficher_logo_sidebar() -> None:
    """Monogramme "SC" + nom de l'appli, en CSS pur (pas de fichier image —
    cf. décision actée dans le spec refonte design). Affiché en haut de la
    sidebar une fois connecté (afficher_sidebar_utilisateur) et sur l'écran
    de connexion (afficher_login), pour une identité visible dès le login."""
    st.sidebar.markdown(
        """
        <div class="sc-logo-bloc">
            <div class="sc-logo-monogramme">SC</div>
            <div class="sc-logo-nom">Planning<br/>Sainte-Croix</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def afficher_login() -> None:
    afficher_logo_sidebar()
    st.title("Planning Médecins — Connexion")
    with st.form("login_form"):
        username = st.text_input("Identifiant")
        password = st.text_input("Mot de passe", type="password")
        submit = st.form_submit_button("Se connecter")

    if submit:
        user = authenticate(username, password)
        if user is None:
            st.error("Identifiant ou mot de passe incorrect.")
        else:
            st.session_state["user"] = {
                "id": user.id,
                "username": user.username,
                "role": user.role,
                "medecin_id": user.medecin_id,
            }
            st.rerun()


def require_login(roles: Optional[list] = None) -> dict:
    """À appeler en haut de chaque page. Stoppe le rendu si non connecté ou
    rôle non autorisé."""
    if "user" not in st.session_state:
        st.warning("Merci de te connecter depuis la page d'accueil (menu de gauche).")
        st.stop()
    user = st.session_state["user"]
    if roles and user["role"] not in roles:
        st.error(f"Accès non autorisé : cette page nécessite le rôle {roles}, tu as le rôle '{user['role']}'.")
        st.stop()
    return user


def afficher_sidebar_utilisateur() -> None:
    afficher_logo_sidebar()
    user = st.session_state.get("user")
    if user:
        st.sidebar.markdown(f"Connecté : **{user['username']}** ({user['role']})")
        if st.sidebar.button("Se déconnecter"):
            del st.session_state["user"]
            st.rerun()
