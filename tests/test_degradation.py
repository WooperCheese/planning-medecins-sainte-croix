from app.db.models import Affectation, StatutAffectation
from app.solver.generation import generer_mois, reinitialiser_mois
from tests.conftest import creer_medecins

ANNEE, MOIS = 2026, 9


def test_penurie_declenche_la_degradation_dans_le_bon_ordre(session):
    # Le seuil de faisabilité par heures est le même chaque semaine du mois
    # (le mois n'est qu'une succession de semaines soumises individuellement
    # à la limite de 50h) : avec 7 médecins, la demande complète et l'étape 1
    # seule restent infaisables ; il faut les deux étapes de dégradation.
    creer_medecins(session, 7)
    session.commit()

    resultat = generer_mois(session, ANNEE, MOIS, "admin")
    session.commit()

    assert resultat.faisable, resultat.message
    assert len(resultat.postes_sacrifies) == 2
    assert "Bridge" in resultat.postes_sacrifies[0]
    assert "Secteur 3" in resultat.postes_sacrifies[1]

    from app.db.models import Affectation

    degradees = session.query(Affectation).filter(Affectation.degrade.is_(True)).count()
    assert degradees > 0


def test_effectif_confortable_ne_declenche_aucune_degradation(session):
    creer_medecins(session, 15)
    session.commit()

    resultat = generer_mois(session, ANNEE, MOIS, "admin")
    session.commit()

    assert resultat.faisable
    assert resultat.postes_sacrifies == []


def test_effectif_trop_faible_reste_infaisable(session):
    creer_medecins(session, 6)
    session.commit()

    resultat = generer_mois(session, ANNEE, MOIS, "admin")
    session.commit()

    assert not resultat.faisable
    assert resultat.affectations == []


def test_regeneration_apres_modification_manuelle_ne_plante_pas(session):
    # Reproduit le scénario du bug signalé : générer une première fois, modifier
    # manuellement une affectation, puis régénérer. Ne doit jamais lever
    # d'IntegrityError (contrainte UNIQUE date/poste/medecin), même si le
    # solveur reproduit par coïncidence le même triplet qu'une ligne manuelle.
    medecins = creer_medecins(session, 15)
    session.commit()

    resultat1 = generer_mois(session, ANNEE, MOIS, "admin")
    session.commit()
    assert resultat1.faisable

    # On force une modification manuelle qui coïncide exactement avec une
    # affectation déjà générée, pour maximiser la chance de collision réelle.
    premiere = resultat1.affectations[0]
    date, poste_code, medecin_id = premiere
    session.query(Affectation).filter(
        Affectation.date == date, Affectation.poste_code == poste_code, Affectation.medecin_id == medecin_id
    ).update({"statut": StatutAffectation.MODIFIE_MANUELLEMENT.value})
    session.commit()

    resultat2 = generer_mois(session, ANNEE, MOIS, "admin")  # ne doit pas lever d'exception
    session.commit()
    assert resultat2.faisable


def test_reinitialiser_mois_supprime_tout_y_compris_manuel(session):
    creer_medecins(session, 15)
    session.commit()

    resultat = generer_mois(session, ANNEE, MOIS, "admin")
    session.commit()
    assert resultat.faisable

    # Marque une ligne comme modifiée manuellement pour vérifier qu'elle est
    # bien supprimée aussi (contrairement à une régénération classique).
    date, poste_code, medecin_id = resultat.affectations[0]
    session.query(Affectation).filter(
        Affectation.date == date, Affectation.poste_code == poste_code, Affectation.medecin_id == medecin_id
    ).update({"statut": StatutAffectation.MODIFIE_MANUELLEMENT.value})
    session.commit()

    nb_avant = session.query(Affectation).count()
    assert nb_avant > 0

    nb_supprimees = reinitialiser_mois(session, ANNEE, MOIS)
    session.commit()

    assert nb_supprimees == nb_avant
    assert session.query(Affectation).count() == 0
