"""
Vérifie la logique de résolution de l'URL de base (app/db/session.py),
introduite pour l'hébergement réel (Streamlit Community Cloud + Neon) :
st.secrets["DATABASE_URL"] > variable d'environnement DATABASE_URL > SQLite
local. Cf. docs/superpowers/specs/2026-07-20-hebergement-reel-design.md.

Ces tests n'ont pas besoin d'une vraie base Postgres : on vérifie uniquement
la CHAÎNE retournée par la fonction de résolution, pas la connexion.
"""

from app.db.session import DB_PATH, _resoudre_db_url


def test_resolution_retombe_sur_sqlite_par_defaut(monkeypatch):
    # Aucun fichier .streamlit/secrets.toml n'existe dans l'environnement de
    # test (non commité, cf. .gitignore), donc _lire_secret_streamlit()
    # échoue silencieusement quel que soit l'état ; il suffit ici de
    # s'assurer qu'aucune variable d'environnement DATABASE_URL ne traîne.
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert _resoudre_db_url() == "sqlite:///{}".format(DB_PATH)


def test_resolution_utilise_database_url_si_definie(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@host/db")
    assert _resoudre_db_url() == "postgresql://user:pass@host/db"


def test_resolution_ignore_database_url_vide(monkeypatch):
    # Une variable d'environnement définie mais vide ne doit pas être prise
    # pour une vraie configuration : on retombe sur SQLite.
    monkeypatch.setenv("DATABASE_URL", "")
    assert _resoudre_db_url() == "sqlite:///{}".format(DB_PATH)
