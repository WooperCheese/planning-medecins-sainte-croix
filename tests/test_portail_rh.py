import datetime
import io

import pandas as pd

from app.db.models import Affectation, HeureSup
from app.rh.paie import generer_export_excel, heures_prevues_par_medecin, heures_sup_par_medecin
from tests.conftest import creer_medecins

PREMIER_JOUR = datetime.date(2026, 9, 1)
DERNIER_JOUR = datetime.date(2026, 9, 30)


def test_heures_prevues_par_medecin_somme_correctement(session):
    medecins = creer_medecins(session, 2)
    session.commit()

    session.add_all(
        [
            # Médecin 0 : deux postes de 10h dans le mois (SECTEUR_1 = 10h).
            Affectation(date=datetime.date(2026, 9, 3), poste_code="SECTEUR_1", medecin_id=medecins[0].id),
            Affectation(date=datetime.date(2026, 9, 4), poste_code="SECTEUR_1", medecin_id=medecins[0].id),
            # Médecin 1 : une garde de nuit (12h) dans le mois.
            Affectation(date=datetime.date(2026, 9, 5), poste_code="GARDE_NUIT", medecin_id=medecins[1].id),
            # Hors période : ne doit pas être compté.
            Affectation(date=datetime.date(2026, 10, 1), poste_code="SECTEUR_1", medecin_id=medecins[0].id),
        ]
    )
    session.commit()

    result = heures_prevues_par_medecin(session, medecins, PREMIER_JOUR, DERNIER_JOUR)

    assert result[medecins[0].id] == 20.0
    assert result[medecins[1].id] == 12.0


def test_heures_sup_par_medecin_somme_correctement(session):
    medecins = creer_medecins(session, 2)
    session.commit()

    session.add_all(
        [
            HeureSup(medecin_id=medecins[0].id, date=datetime.date(2026, 9, 10), nb_heures=2.5, motif="Renfort"),
            HeureSup(medecin_id=medecins[0].id, date=datetime.date(2026, 9, 20), nb_heures=1.5, motif="Renfort"),
            HeureSup(medecin_id=medecins[1].id, date=datetime.date(2026, 9, 15), nb_heures=3.0, motif="Renfort"),
            # Hors période.
            HeureSup(medecin_id=medecins[0].id, date=datetime.date(2026, 8, 31), nb_heures=99.0, motif="Hors mois"),
        ]
    )
    session.commit()

    result = heures_sup_par_medecin(session, medecins, PREMIER_JOUR, DERNIER_JOUR)

    assert result[medecins[0].id] == 4.0
    assert result[medecins[1].id] == 3.0


def test_generer_export_excel_contient_les_bonnes_valeurs(session):
    medecins = creer_medecins(session, 2, prefixe="Z")
    session.commit()

    heures_prevues = {medecins[0].id: 20.0, medecins[1].id: 12.0}
    heures_sup = {medecins[0].id: 4.0, medecins[1].id: 0.0}

    contenu = generer_export_excel(medecins, heures_prevues, heures_sup)
    assert isinstance(contenu, bytes)
    assert len(contenu) > 0

    df = pd.read_excel(io.BytesIO(contenu), sheet_name="Paie")
    assert list(df.columns) == ["Médecin", "Heures prévues", "Heures sup", "Total"]
    # 2 médecins + 1 ligne TOTAL.
    assert len(df) == 3

    ligne_totale = df[df["Médecin"] == "TOTAL"].iloc[0]
    assert ligne_totale["Heures prévues"] == 32.0
    assert ligne_totale["Heures sup"] == 4.0
    assert ligne_totale["Total"] == 36.0
