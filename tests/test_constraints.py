import datetime

from app.config import LIMITES
from app.db.models import Affectation
from app.solver.calendar_ch import jour_semaine_fr
from app.solver.generation import generer_mois
from tests.conftest import creer_medecins

# Septembre 2026 démarre un mardi : bloc de nuit "frais", pas de continuation
# nécessaire depuis le mois précédent. Pratique comme mois de référence pour
# les tests qui ne portent pas spécifiquement sur la continuité inter-mois.
ANNEE, MOIS = 2026, 9
PREMIER_JOUR = datetime.date(ANNEE, MOIS, 1)

DUREE_PAR_POSTE = {
    "POLY_MATIN": 10,
    "POLY_JOURNEE": 10,
    "APRES_MIDI": 9,
    "SECTEUR_1": 10,
    "SECTEUR_2": 10,
    "SECTEUR_3": 10,
    "GARDE_NUIT": 12,
    "SAM_JOUR_COURT": 8,
    "SAM_JOUR_LONG": 12,
    "DIM_JOUR_UNIQUE": 12,
}


def test_premier_jour_est_bien_un_mardi():
    assert PREMIER_JOUR.weekday() == 1  # 0=lundi, 1=mardi


def test_generation_mensuelle_faisable_et_sans_sacrifice(session):
    creer_medecins(session, 15)
    session.commit()

    resultat = generer_mois(session, ANNEE, MOIS, "admin")
    session.commit()

    assert resultat.faisable
    assert resultat.postes_sacrifies == []
    assert len(resultat.affectations) > 0


def test_pas_de_double_affectation_meme_jour(session):
    creer_medecins(session, 15)
    session.commit()
    resultat = generer_mois(session, ANNEE, MOIS, "admin")
    session.commit()

    par_medecin_jour: dict = {}
    for date, poste_code, medecin_id in resultat.affectations:
        key = (medecin_id, date)
        par_medecin_jour[key] = par_medecin_jour.get(key, 0) + 1

    assert all(count <= 1 for count in par_medecin_jour.values())


def test_max_50h_par_semaine_calendaire(session):
    creer_medecins(session, 15)
    session.commit()
    resultat = generer_mois(session, ANNEE, MOIS, "admin")
    session.commit()

    heures_par_semaine: dict = {}
    for date, poste_code, medecin_id in resultat.affectations:
        lundi_semaine = date - datetime.timedelta(days=date.weekday())
        key = (medecin_id, lundi_semaine)
        heures_par_semaine[key] = heures_par_semaine.get(key, 0) + DUREE_PAR_POSTE[poste_code]

    depassements = {k: v for k, v in heures_par_semaine.items() if v > LIMITES["max_heures_semaine"]}
    assert depassements == {}, depassements


def test_blocs_de_nuit_jamais_isoles(session):
    creer_medecins(session, 15)
    session.commit()
    resultat = generer_mois(session, ANNEE, MOIS, "admin")
    session.commit()

    nuits_par_date = {
        date: medecin_id for date, poste_code, medecin_id in resultat.affectations if poste_code == "GARDE_NUIT"
    }

    # Pour chaque garde de nuit, vérifie qu'elle appartient bien à un bloc
    # cohérent : mar-mer-jeu (même médecin les 3 jours si tous présents) ou
    # ven-sam-dim-lun (même médecin sur les jours présents).
    d = PREMIER_JOUR
    while d.month == MOIS:
        label = jour_semaine_fr(d)
        if label == "mardi":
            jours_bloc = [d, d + datetime.timedelta(days=1), d + datetime.timedelta(days=2)]
        elif label == "vendredi":
            jours_bloc = [d + datetime.timedelta(days=i) for i in range(4)]
        else:
            d += datetime.timedelta(days=1)
            continue

        medecins_bloc = {nuits_par_date[j] for j in jours_bloc if j in nuits_par_date and j.month == MOIS}
        assert len(medecins_bloc) <= 1, "bloc de nuit incohérent démarrant le {}".format(d)
        d += datetime.timedelta(days=1)


def test_jumelage_weekend_journee_longue(session):
    creer_medecins(session, 15)
    session.commit()
    resultat = generer_mois(session, ANNEE, MOIS, "admin")
    session.commit()

    par_date_poste: dict = {}
    for date, poste_code, medecin_id in resultat.affectations:
        par_date_poste.setdefault((date, poste_code), []).append(medecin_id)

    d = PREMIER_JOUR
    while d.month == MOIS:
        if jour_semaine_fr(d) == "samedi":
            dimanche = d + datetime.timedelta(days=1)
            if dimanche.month == MOIS:
                med_samedi = par_date_poste.get((d, "SAM_JOUR_LONG"), [None])[0]
                med_dimanche = par_date_poste.get((dimanche, "DIM_JOUR_UNIQUE"), [None])[0]
                assert med_samedi is not None and med_samedi == med_dimanche, (
                    "jumelage week-end rompu le {} / {}".format(d, dimanche)
                )
        d += datetime.timedelta(days=1)


def test_continuite_bloc_debut_mois_et_repos(session):
    # Août 2026 démarre un samedi : c'est la continuation (jours 2-3-4 du bloc
    # ven-sam-dim-lun) d'un bloc entamé le vendredi 31 juillet (mois précédent).
    medecins = creer_medecins(session, 15)
    session.commit()

    vendredi_precedent = datetime.date(2026, 7, 31)
    session.add(
        Affectation(
            date=vendredi_precedent,
            poste_code="GARDE_NUIT",
            medecin_id=medecins[0].id,
            statut="genere",
        )
    )
    session.commit()

    resultat = generer_mois(session, 2026, 8, "admin")
    session.commit()
    assert resultat.faisable

    nuits_par_date = {
        date: medecin_id for date, poste_code, medecin_id in resultat.affectations if poste_code == "GARDE_NUIT"
    }
    # 1er, 2 et 3 août (samedi, dimanche, lundi) doivent continuer sur medecins[0].
    for jour in (datetime.date(2026, 8, 1), datetime.date(2026, 8, 2), datetime.date(2026, 8, 3)):
        assert nuits_par_date.get(jour) == medecins[0].id

    # Repos ensuite (mardi 4, mercredi 5 août) : le médecin ne doit rien faire.
    jours_repos = [datetime.date(2026, 8, 4), datetime.date(2026, 8, 5)]
    for date, poste_code, medecin_id in resultat.affectations:
        if medecin_id == medecins[0].id:
            assert date not in jours_repos


def test_secteur_stable_toute_la_semaine(session):
    # Vérifie la contrainte de continuité des soins : sur une même semaine
    # calendaire (lundi-vendredi), un Secteur (1, 2 ou 3) ne doit jamais être
    # "relayé" entre plusieurs médecins sans justification. Toute journée où
    # un médecin autre que le titulaire majoritaire de la semaine occupe le
    # secteur doit être justifiée par une Garde de Nuit de ce titulaire ce
    # jour précis (aucun congé n'est semé dans ce test, donc pas d'autre
    # justification possible).
    creer_medecins(session, 15)
    session.commit()
    resultat = generer_mois(session, ANNEE, MOIS, "admin")
    session.commit()
    assert resultat.faisable

    nuits_par_date = {
        date: medecin_id for date, poste_code, medecin_id in resultat.affectations if poste_code == "GARDE_NUIT"
    }

    for secteur_code in ("SECTEUR_1", "SECTEUR_2", "SECTEUR_3"):
        par_semaine: dict = {}
        for date, poste_code, medecin_id in resultat.affectations:
            if poste_code != secteur_code:
                continue
            lundi_semaine = date - datetime.timedelta(days=date.weekday())
            par_semaine.setdefault(lundi_semaine, []).append((date, medecin_id))

        for lundi_semaine, occurrences in par_semaine.items():
            distincts = {medecin_id for _date, medecin_id in occurrences}
            if len(distincts) <= 1:
                continue  # cas normal : un seul titulaire toute la semaine

            # Plus d'un médecin cette semaine : il doit exister AU MOINS UN
            # candidat titulaire qui justifie tous les relais observés (chaque
            # jour couvert par quelqu'un d'autre correspond à une Garde de
            # Nuit de ce candidat ce jour précis). Le titulaire n'est pas
            # forcément celui qui a travaillé le plus de jours : s'il enchaîne
            # un bloc de nuit de 3 jours (mar-mer-jeu) au milieu de sa propre
            # semaine de secteur, il peut travailler MOINS de jours que les
            # remplaçants qui couvrent ce bloc.
            titulaire_valide = None
            for candidat in distincts:
                justifie = True
                for date, medecin_id in occurrences:
                    if medecin_id == candidat:
                        continue
                    if nuits_par_date.get(date) != candidat:
                        justifie = False
                        break
                if justifie:
                    titulaire_valide = candidat
                    break

            assert titulaire_valide is not None, (
                "secteur {} semaine du {} : aucun médecin ne justifie les relais observés {}".format(
                    secteur_code, lundi_semaine, occurrences
                )
            )
