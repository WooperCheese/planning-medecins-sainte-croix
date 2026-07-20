"""
Connexion à la base de données + helpers de session.

Résolution de l'URL de connexion, par ordre de priorité :
1. st.secrets["DATABASE_URL"] — cas du déploiement sur Streamlit Community
   Cloud, où le secret est configuré directement dans l'interface de la
   plateforme (jamais commité dans le code). L'accès à st.secrets est protégé
   par un try/except : en local (aucun fichier .streamlit/secrets.toml), cet
   accès échoue silencieusement et on passe à l'étape suivante — aucun impact
   sur les tests ni le développement local.
2. Variable d'environnement DATABASE_URL — utile par exemple pour lancer le
   script de seed en local en pointant vers une base Postgres distante (cf.
   docs/DEPLOIEMENT.md), sans avoir à écrire de secrets.toml.
3. SQLite via PLANNING_DB_PATH — comportement historique, utilisé par les
   tests (cf. tests/conftest.py) et le développement local sans configuration
   supplémentaire.

Cf. docs/superpowers/specs/2026-07-20-hebergement-reel-design.md pour le
design complet (compromis assumé : ce module importe streamlit pour lire
st.secrets, léger couplage jugé acceptable vu la taille du projet).

100% compatible Python 3.9 : Optional[...] partout, jamais de `X | None`.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Optional

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base

DB_PATH = os.environ.get(
    "PLANNING_DB_PATH", os.path.join(os.path.dirname(__file__), "..", "..", "planning.db")
)


def _lire_secret_streamlit() -> Optional[str]:
    """Tente de lire st.secrets["DATABASE_URL"]. Retourne None dans tous les
    cas où ce n'est pas possible (streamlit non disponible, aucun fichier de
    secrets, clé absente) plutôt que de lever une exception : c'est le cas
    normal en local/tests, pas une erreur."""
    try:
        import streamlit as st

        if "DATABASE_URL" in st.secrets:
            return st.secrets["DATABASE_URL"]
    except Exception:
        pass
    return None


def _resoudre_db_url() -> str:
    """Applique l'ordre de priorité décrit en tête de module."""
    secret = _lire_secret_streamlit()
    if secret:
        return secret

    env_url = os.environ.get("DATABASE_URL")
    if env_url:
        return env_url

    return "sqlite:///{}".format(DB_PATH)


DB_URL = _resoudre_db_url()

# check_same_thread=False est une option spécifique au driver SQLite (Streamlit
# exécute chaque rerun dans son propre thread) : elle ne doit jamais être
# transmise à un moteur PostgreSQL, qui ne la reconnaît pas.
if DB_URL.startswith("sqlite:///"):
    engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DB_URL)

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def _colonnes_a_ajouter_si_manquantes():
    """Colonnes introduites après la création initiale du schéma. create_all()
    ne modifie JAMAIS une table déjà existante (seulement les tables encore
    absentes) : sur une base déjà initialisée (ex : Neon en production), ces
    colonnes doivent être ajoutées explicitement. Format :
    (table, colonne, définition SQL). Compatible SQLite et PostgreSQL."""
    return [
        ("indisponibilites", "statut", "VARCHAR(20) DEFAULT 'validee' NOT NULL"),
    ]


def _appliquer_migrations_legeres() -> None:
    inspecteur = inspect(engine)
    tables_existantes = set(inspecteur.get_table_names())
    for table, colonne, definition in _colonnes_a_ajouter_si_manquantes():
        if table not in tables_existantes:
            continue  # table pas encore créée : create_all() lui donnera directement la bonne colonne
        colonnes_existantes = {c["name"] for c in inspecteur.get_columns(table)}
        if colonne in colonnes_existantes:
            continue
        with engine.begin() as connexion:
            connexion.execute(text("ALTER TABLE {} ADD COLUMN {} {}".format(table, colonne, definition)))


def init_db() -> None:
    """Crée toutes les tables si elles n'existent pas encore, puis applique
    les migrations légères nécessaires sur les tables déjà existantes (cf.
    _appliquer_migrations_legeres)."""
    Base.metadata.create_all(engine)
    _appliquer_migrations_legeres()


@contextmanager
def get_session():
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
