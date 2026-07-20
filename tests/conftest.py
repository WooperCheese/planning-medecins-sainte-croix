import datetime
import os
import sys
import tempfile

import pytest

# La base doit être configurée AVANT le premier import de app.db.session
# (le moteur SQLAlchemy est créé au chargement du module).
_tmp_db_fd, _tmp_db_path = tempfile.mkstemp(suffix=".db")
os.close(_tmp_db_fd)
os.environ["PLANNING_DB_PATH"] = _tmp_db_path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.models import Base, Cohorte, Medecin  # noqa: E402
from app.db.session import engine, get_session  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


def creer_medecins(session, n: int, prefixe: str = "M") -> list[Medecin]:
    cohorte = Cohorte(
        label="Cohorte Test",
        date_debut=datetime.date(2025, 11, 1),
        date_fin=datetime.date(2026, 5, 1),
        archivee=False,
    )
    session.add(cohorte)
    session.flush()

    medecins = []
    for i in range(n):
        m = Medecin(
            nom=f"{prefixe}{i:02d}",
            prenom="Test",
            cohorte_id=cohorte.id,
            actif=True,
            date_arrivee=datetime.date(2025, 11, 1),
            date_depart=None,
        )
        session.add(m)
        medecins.append(m)
    session.flush()
    return medecins


@pytest.fixture
def session(_reset_db):
    with get_session() as s:
        yield s
