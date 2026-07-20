from app.auth.auth import authenticate
from app.auth.comptes import (
    AncienMotDePasseIncorrect,
    IdentifiantDejaUtilise,
    changer_propre_mot_de_passe,
    creer_compte,
    creer_compte_medecin,
    supprimer_compte,
)
from app.db.models import Role, User
from tests.conftest import creer_medecins


def test_creer_compte_admin_sans_medecin_lie(session):
    mot_de_passe = creer_compte(session, "a.test", Role.ADMIN.value)
    session.commit()

    user = authenticate("a.test", mot_de_passe)
    assert user is not None
    assert user.role == "admin"
    assert user.medecin_id is None


def test_creer_compte_rh_sans_medecin_lie(session):
    mot_de_passe = creer_compte(session, "r.test", Role.RH.value)
    session.commit()

    user = authenticate("r.test", mot_de_passe)
    assert user is not None
    assert user.role == "rh"
    assert user.medecin_id is None


def test_creer_compte_refuse_identifiant_deja_pris_quel_que_soit_le_role(session):
    creer_compte(session, "x.test", Role.ADMIN.value)
    session.commit()

    try:
        creer_compte(session, "x.test", Role.RH.value)
        assert False, "IdentifiantDejaUtilise aurait dû être levée"
    except IdentifiantDejaUtilise:
        pass


def test_creer_compte_medecin_toujours_fonctionnel_apres_refactor(session):
    # Comportement existant préservé : creer_compte_medecin() reste utilisable
    # avec la même signature qu'avant le refactor.
    medecins = creer_medecins(session, 1)
    session.commit()

    mot_de_passe = creer_compte_medecin(session, medecins[0].id, "m.test")
    session.commit()

    user = authenticate("m.test", mot_de_passe)
    assert user is not None
    assert user.role == "medecin"
    assert user.medecin_id == medecins[0].id


def test_changer_propre_mot_de_passe_avec_ancien_correct(session):
    mot_de_passe = creer_compte(session, "a.test", Role.ADMIN.value)
    session.commit()

    user = authenticate("a.test", mot_de_passe)
    changer_propre_mot_de_passe(session, user.id, mot_de_passe, "nouveaumdp123")
    session.commit()

    assert authenticate("a.test", mot_de_passe) is None
    assert authenticate("a.test", "nouveaumdp123") is not None


def test_changer_propre_mot_de_passe_avec_ancien_incorrect(session):
    mot_de_passe = creer_compte(session, "a.test", Role.ADMIN.value)
    session.commit()

    user = authenticate("a.test", mot_de_passe)

    try:
        changer_propre_mot_de_passe(session, user.id, "mauvais_mdp", "nouveaumdp123")
        assert False, "AncienMotDePasseIncorrect aurait dû être levée"
    except AncienMotDePasseIncorrect:
        pass
    session.commit()

    # Rien n'a changé : l'ancien mot de passe fonctionne toujours.
    assert authenticate("a.test", mot_de_passe) is not None
    assert authenticate("a.test", "nouveaumdp123") is None


def test_supprimer_compte_sans_medecin_lie(session):
    mot_de_passe = creer_compte(session, "a.test", Role.ADMIN.value)
    session.commit()
    user = authenticate("a.test", mot_de_passe)

    supprimer_compte(session, user.id)
    session.commit()

    assert authenticate("a.test", mot_de_passe) is None
    assert session.query(User).filter_by(username="a.test").first() is None


def test_supprimer_compte_medecin_preserve_la_fiche_medecin(session):
    medecins = creer_medecins(session, 1)
    session.commit()

    mot_de_passe = creer_compte_medecin(session, medecins[0].id, "m.test")
    session.commit()
    user = authenticate("m.test", mot_de_passe)

    supprimer_compte(session, user.id)
    session.commit()

    assert authenticate("m.test", mot_de_passe) is None
    # La fiche médecin liée n'est pas affectée par la suppression du compte.
    medecin_restant = session.get(medecins[0].__class__, medecins[0].id)
    assert medecin_restant is not None
    assert medecin_restant.actif is True
