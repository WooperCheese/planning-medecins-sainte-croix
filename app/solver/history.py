"""
Lecture de l'historique (mémoire glissante) nécessaire avant de générer un
nouveau mois :

- médecins actifs et leurs indisponibilités sur le mois à générer
- score d'équité (nuits + jours de week-end) sur les MEMOIRE_JOURS derniers jours
- séquence "Secteur" en cours (streak, tous secteurs confondus) pour respecter durée min/max
- titulaire de chaque secteur sur la dernière semaine connue, pour prolonger le
  bonus de continuité de l'objectif au-delà de la frontière du mois
- bloc de nuit entamé le mois précédent et qui déborde sur le début de ce mois
  (bloc mar-mer-jeu ou bloc ven-sam-dim-lun) : le médecin concerné doit
  continuer ce bloc, avec le repos qui suit si c'est le bloc week-end
- heures déjà travaillées sur la semaine calendaire à cheval entre le mois
  précédent et celui-ci, pour ne pas dépasser 50h/semaine en comptant les deux

Tout ceci lit uniquement la base (Affectation, Indisponibilite, Medecin), aucune
variable de décision : c'est du contexte fixe pour le solver.

100% compatible Python 3.9 : Optional[...] partout, jamais de `X | None`.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from app.config import MEMOIRE_JOURS, POSTES_SECTEURS, get_postes_du_jour
from app.db.models import Affectation, Indisponibilite, Medecin
from app.solver.calendar_ch import est_ferie, jour_semaine_fr

JOURS_WEEKEND = {"samedi", "dimanche"}

# Motifs des blocs de nuit (doivent rester synchronisés avec app.config.REGLES_ROTATION).
BLOC_SEMAINE_LABELS = ["mardi", "mercredi", "jeudi"]
BLOC_WEEKEND_LABELS = ["vendredi", "samedi", "dimanche", "lundi"]


@dataclass
class Contexte:
    medecins: List[Medecin]
    indispo_par_medecin: Dict[int, Set[datetime.date]]
    score_equite: Dict[int, int]  # nuits + jours we sur la fenêtre mémoire
    service_streak_semaines: Dict[int, int]  # nb semaines consécutives en service jusqu'à la précédente
    en_service_semaine_precedente: Set[int]
    # Continuité d'un bloc de nuit entamé le mois précédent :
    medecin_bloc_a_forcer: Optional[int]
    jours_bloc_a_forcer: List[datetime.date]  # jours, en tout début de période, à forcer pour ce médecin
    bloc_a_forcer_est_weekend: bool  # True si c'est le bloc ven-sam-dim-lun (déclenche le repos qui suit)
    # Heures déjà travaillées sur la semaine calendaire à cheval avec le mois précédent :
    heures_semaine_partielle_precedente: Dict[int, int]
    # Titulaire de chaque secteur (SECTEUR_1/2/3) sur la dernière semaine calendaire
    # avant le début de la période, pour prolonger la continuité au-delà de la
    # frontière du mois (objectif soft, cf. app.solver.objective.add_equite).
    # None si aucun titulaire clair (bootstrap, ou secteur non attribué la semaine passée).
    titulaire_secteur_semaine_precedente: Dict[str, Optional[int]]


def _medecins_actifs(session: Session, premier_jour: datetime.date, dernier_jour: datetime.date) -> List[Medecin]:
    tous = session.query(Medecin).filter(Medecin.actif.is_(True)).all()
    actifs = []
    for m in tous:
        if m.date_arrivee > dernier_jour:
            continue
        if m.date_depart is not None and m.date_depart < premier_jour:
            continue
        actifs.append(m)
    return actifs


def indisponibilites_par_medecin(
    session: Session, medecins: List[Medecin], premier_jour: datetime.date, dernier_jour: datetime.date
) -> Dict[int, set]:
    """Fonction publique (réutilisée par l'UI, ex : vue par médecin de la page
    Planning, pas seulement par le solveur)."""
    result: Dict[int, Set[datetime.date]] = {m.id: set() for m in medecins}
    ids = [m.id for m in medecins]
    if not ids:
        return result
    indispos = (
        session.query(Indisponibilite)
        .filter(Indisponibilite.medecin_id.in_(ids))
        .filter(Indisponibilite.date_debut <= dernier_jour)
        .filter(Indisponibilite.date_fin >= premier_jour)
        .all()
    )
    for i in indispos:
        d = max(i.date_debut, premier_jour)
        fin = min(i.date_fin, dernier_jour)
        while d <= fin:
            result.setdefault(i.medecin_id, set()).add(d)
            d += datetime.timedelta(days=1)
    return result


def _score_equite(session: Session, medecins: List[Medecin], premier_jour: datetime.date) -> Dict[int, int]:
    debut_fenetre = premier_jour - datetime.timedelta(days=MEMOIRE_JOURS)
    ids = [m.id for m in medecins]
    score = {m.id: 0 for m in medecins}
    if not ids:
        return score
    affectations = (
        session.query(Affectation)
        .filter(Affectation.medecin_id.in_(ids))
        .filter(Affectation.date >= debut_fenetre)
        .filter(Affectation.date < premier_jour)
        .all()
    )
    for a in affectations:
        jour = jour_semaine_fr(a.date)
        if a.poste_code == "GARDE_NUIT" or jour in JOURS_WEEKEND:
            score[a.medecin_id] = score.get(a.medecin_id, 0) + 1
    return score


def _service_streaks(
    session: Session, medecins: List[Medecin], premier_jour: datetime.date
) -> Tuple[Dict[int, int], Set[int]]:
    """Compte le nombre de fenêtres de 7 jours consécutives (se terminant juste
    avant premier_jour) où chaque médecin a eu au moins un jour sur un Secteur
    (1, 2 ou 3 confondus — ce streak porte sur l'activité "secteur" en général,
    pas sur un secteur précis ; cf. _titulaire_secteur_semaine_precedente et
    add_stabilite_secteur_hebdomadaire pour la continuité PAR secteur).
    """
    ids = [m.id for m in medecins]
    streak: Dict[int, int] = {m.id: 0 for m in medecins}
    en_service_precedente: Set[int] = set()
    if not ids:
        return streak, en_service_precedente

    for m_id in ids:
        semaine_fin = premier_jour
        compte = 0
        while compte < 12:  # garde-fou, pas besoin de remonter indéfiniment
            semaine_debut = semaine_fin - datetime.timedelta(days=7)
            nb = (
                session.query(Affectation)
                .filter(
                    Affectation.medecin_id == m_id,
                    Affectation.poste_code.in_(POSTES_SECTEURS),
                    Affectation.date >= semaine_debut,
                    Affectation.date < semaine_fin,
                )
                .count()
            )
            if nb == 0:
                break
            compte += 1
            if compte == 1:
                en_service_precedente.add(m_id)
            semaine_fin = semaine_debut
        streak[m_id] = compte
    return streak, en_service_precedente


def _bloc_a_forcer_debut_periode(
    session: Session, premier_jour: datetime.date
) -> Tuple[Optional[int], List[datetime.date], bool]:
    """Si la période à générer démarre au milieu d'un bloc de nuit entamé le
    mois précédent (bloc mar-mer-jeu ou bloc ven-sam-dim-lun), retourne
    (medecin_id, jours_a_forcer_ce_mois, est_bloc_weekend).

    Sinon (aucune continuation nécessaire, ou historique incomplet/incohérent),
    retourne (None, [], False) : la période démarre "propre".
    """
    label_premier_jour = jour_semaine_fr(premier_jour)

    for pattern, est_weekend in ((BLOC_SEMAINE_LABELS, False), (BLOC_WEEKEND_LABELS, True)):
        if label_premier_jour not in pattern:
            continue
        position = pattern.index(label_premier_jour)
        if position == 0:
            continue  # la période démarre pile au début d'un bloc : rien à forcer, le lien se fera en interne

        jours_precedents = [premier_jour - datetime.timedelta(days=position - i) for i in range(position)]
        affectations = {
            a.date: a.medecin_id
            for a in session.query(Affectation)
            .filter(Affectation.poste_code == "GARDE_NUIT", Affectation.date.in_(jours_precedents))
            .all()
        }
        if len(affectations) != len(jours_precedents):
            continue  # historique incomplet (ex : tout premier mois du système) : pas de continuation fiable
        ids = set(affectations.values())
        if len(ids) != 1:
            continue

        medecin_id = ids.pop()
        nb_jours_a_forcer = len(pattern) - position
        jours_a_forcer = [premier_jour + datetime.timedelta(days=i) for i in range(nb_jours_a_forcer)]
        return medecin_id, jours_a_forcer, est_weekend

    return None, [], False


def _titulaire_secteur_semaine_precedente(
    session: Session, premier_jour: datetime.date
) -> Dict[str, Optional[int]]:
    """Pour chaque secteur (SECTEUR_1/2/3), retourne le médecin le plus présent
    sur ce secteur durant les 7 jours précédant premier_jour (majorité simple).
    Sert uniquement à prolonger le bonus de continuité de l'objectif au-delà
    de la frontière du mois ; ce n'est jamais une contrainte dure. None si le
    secteur n'a aucune affectation sur cette fenêtre (bootstrap, mois sans
    historique, etc.)."""
    debut = premier_jour - datetime.timedelta(days=7)
    result: Dict[str, Optional[int]] = {code: None for code in POSTES_SECTEURS}
    affectations = (
        session.query(Affectation)
        .filter(Affectation.poste_code.in_(POSTES_SECTEURS))
        .filter(Affectation.date >= debut, Affectation.date < premier_jour)
        .all()
    )
    comptes: Dict[str, Dict[int, int]] = {code: {} for code in POSTES_SECTEURS}
    for a in affectations:
        comptes[a.poste_code][a.medecin_id] = comptes[a.poste_code].get(a.medecin_id, 0) + 1
    for code, par_medecin in comptes.items():
        if par_medecin:
            result[code] = max(par_medecin, key=par_medecin.get)
    return result


def _heures_semaine_partielle_precedente(session: Session, premier_jour: datetime.date) -> Dict[int, int]:
    """Heures déjà travaillées par chaque médecin sur les jours de la semaine
    calendaire (lundi-dimanche) contenant `premier_jour`, mais tombant AVANT
    `premier_jour` (donc dans le mois précédent). Sert à ne pas dépasser 50h
    sur une semaine à cheval entre deux mois. Dict vide si premier_jour est un
    lundi (aucun jour précédent dans cette semaine)."""
    jours_avant = premier_jour.weekday()  # 0 si lundi
    if jours_avant == 0:
        return {}
    lundi_semaine = premier_jour - datetime.timedelta(days=jours_avant)
    affectations = (
        session.query(Affectation)
        .filter(Affectation.date >= lundi_semaine, Affectation.date < premier_jour)
        .all()
    )
    heures: Dict[int, int] = {}
    for a in affectations:
        label = jour_semaine_fr(a.date)
        duree = 0
        for p in get_postes_du_jour(label, est_ferie(a.date)):
            if p.code == a.poste_code:
                duree = p.duree_h
                break
        heures[a.medecin_id] = heures.get(a.medecin_id, 0) + duree
    return heures


def charger_contexte(session: Session, premier_jour: datetime.date, dernier_jour: datetime.date) -> Contexte:
    medecins = _medecins_actifs(session, premier_jour, dernier_jour)
    indispo = indisponibilites_par_medecin(session, medecins, premier_jour, dernier_jour)
    score = _score_equite(session, medecins, premier_jour)
    streak, en_service_prec = _service_streaks(session, medecins, premier_jour)
    medecin_bloc, jours_bloc, est_weekend = _bloc_a_forcer_debut_periode(session, premier_jour)
    heures_partielles = _heures_semaine_partielle_precedente(session, premier_jour)
    titulaire_secteur_prec = _titulaire_secteur_semaine_precedente(session, premier_jour)

    return Contexte(
        medecins=medecins,
        indispo_par_medecin=indispo,
        score_equite=score,
        service_streak_semaines=streak,
        en_service_semaine_precedente=en_service_prec,
        medecin_bloc_a_forcer=medecin_bloc,
        jours_bloc_a_forcer=jours_bloc,
        bloc_a_forcer_est_weekend=est_weekend,
        heures_semaine_partielle_precedente=heures_partielles,
        titulaire_secteur_semaine_precedente=titulaire_secteur_prec,
    )
