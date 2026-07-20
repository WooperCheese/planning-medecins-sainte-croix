import datetime

from app.auth.auth import authenticate
from app.auth.comptes import IdentifiantDejaUtilise, creer_compte_medecin, regenerer_mot_de_passe
from app.db.models import HeureSup, Indisponibilite, StatutIndisponibilite
from app.solver.history import indisponibilites_par_medecin
from tests.conftest import creer_medecins

PREMIER_JOUR = datetime.date(2026, 9, 1)
DERNIER_JOUR = datetime.date(2026, 9, 30)


def test_creer_compte_medecin_permet_ensuite_de_se_connecter(session):
    medecins = creer_medecins(session, 1)
    session.commit()

    mot_de_passe = creer_compte_medecin(session, medecins[0].id, "m.test")
    session.commit()

    user = authenticate("m.test", mot_de_passe)
    assert user is not None
    assert user.role == "medecin"
    assert user.medecin_id == medecins[0].id


def test_creer_compte_medecin_refuse_identifiant_deja_pris(session):
    medecins = creer_medecins(session, 2)
    session.commit()

    creer_compte_medecin(session, medecins[0].id, "m.test")
    session.commit()

    try:
        creer_compte_medecin(session, medecins[1].id, "m.test")
        assert False, "IdentifiantDejaUtilise aurait dû être levée"
    except IdentifiantDejaUtilise:
        pass


def test_regenerer_mot_de_passe_invalide_ancien_et_active_nouveau(session):
    medecins = creer_medecins(session, 1)
    session.commit()

    ancien_mdp = creer_compte_medecin(session, medecins[0].id, "m.test")
    session.commit()

    user = authenticate("m.test", ancien_mdp)
    user_id = user.id

    nouveau_mdp = regenerer_mot_de_passe(session, user_id)
    session.commit()

    assert authenticate("m.test", ancien_mdp) is None
    assert authenticate("m.test", nouveau_mdp) is not None


def test_indisponibilites_par_medecin_ignore_les_demandes_en_attente(session):
    medecins = creer_medecins(session, 2)
    session.commit()

    session.add_all(
        [
            Indisponibilite(
                medecin_id=medecins[0].id,
                date_debut=datetime.date(2026, 9, 10),
                date_fin=datetime.date(2026, 9, 12),
                type="conge",
                statut=StatutIndisponibilite.VALIDEE.value,
            ),
            Indisponibilite(
                medecin_id=medecins[1].id,
                date_debut=datetime.date(2026, 9, 15),
                date_fin=datetime.date(2026, 9, 17),
                type="conge",
                statut=StatutIndisponibilite.EN_ATTENTE.value,
            ),
        ]
    )
    session.commit()

    result = indisponibilites_par_medecin(session, medecins, PREMIER_JOUR, DERNIER_JOUR)

    assert datetime.date(2026, 9, 11) in result[medecins[0].id]
    # La demande en attente ne doit PAS bloquer le médecin 2 : son ensemble
    # d'indisponibilités validées reste vide sur cette période.
    assert result[medecins[1].id] == set()


def test_indisponibilite_admin_reste_validee_par_defaut(session):
    # Comportement historique préservé : une indisponibilité créée sans
    # préciser de statut (comme le fait la page admin) est "validee".
    medecins = creer_medecins(session, 1)
    session.commit()

    session.add(
        Indisponibilite(
            medecin_id=medecins[0].id,
            date_debut=datetime.date(2026, 9, 1),
            date_fin=datetime.date(2026, 9, 2),
            type="conge",
        )
    )
    session.commit()

    indispo = session.query(Indisponibilite).first()
    assert indispo.statut == StatutIndisponibilite.VALIDEE.value


def test_heure_sup_ecriture_et_lecture(session):
    medecins = creer_medecins(session, 1)
    session.commit()

    session.add(
        HeureSup(
            medecin_id=medecins[0].id,
            date=datetime.date(2026, 9, 5),
            nb_heures=2.5,
            motif="Renfort garde de nuit",
        )
    )
    session.commit()

    heures = session.query(HeureSup).filter(HeureSup.medecin_id == medecins[0].id).all()
    assert len(heures) == 1
    assert heures[0].nb_heures == 2.5
    assert heures[0].motif == "Renfort garde de nuit"
