"""
Assemblage du modèle CP-SAT : construction des variables, appel des
contraintes et de l'objectif, résolution, extraction de la solution.

Ce module ne connaît pas la logique de dégradation (voir degradation.py) ni la
persistance en base (voir generation.py, seul module qui touche la DB).

L'horizon de génération est le mois civil complet (cf. jours_du_mois) ; toutes
les fonctions ci-dessous restent génériques sur la longueur de `jours`, ce qui
les rend aussi valables sur un horizon plus court si besoin (tests, debug).

100% compatible Python 3.9 : Optional[...] partout, jamais de `X | None`.
"""

from __future__ import annotations

import calendar
import dataclasses
import datetime
from typing import Dict, FrozenSet, List, Optional, Tuple

from ortools.sat.python import cp_model

from app import config
from app.solver import constraints, objective
from app.solver.calendar_ch import est_ferie, jour_semaine_fr
from app.solver.history import Contexte

VariableDict = Dict[Tuple[int, int, str], cp_model.IntVar]

# Horizon mensuel = problème nettement plus gros qu'une semaine : on laisse
# plus de temps au solveur.
TEMPS_MAX_RESOLUTION_S = 60


def jours_de_la_semaine(lundi: datetime.date) -> List[datetime.date]:
    """Utilitaire encore utilisé ponctuellement (ex : tests, regroupements
    hebdomadaires dans l'UI). La génération elle-même utilise jours_du_mois."""
    return [lundi + datetime.timedelta(days=i) for i in range(7)]


def jours_du_mois(annee: int, mois: int) -> List[datetime.date]:
    """Retourne la liste de tous les jours (1 au 28/29/30/31) du mois civil
    donné, dans l'ordre."""
    nb_jours = calendar.monthrange(annee, mois)[1]
    premier_jour = datetime.date(annee, mois, 1)
    return [premier_jour + datetime.timedelta(days=i) for i in range(nb_jours)]


def calculer_postes_periode(
    jours: List[datetime.date],
    postes_retires: FrozenSet[str] = frozenset(),
    effectifs_reduits: Optional[dict] = None,
) -> Tuple[Dict[int, List[config.PosteConfig]], List[str]]:
    """Retourne, pour chaque jour (index 0 à len(jours)-1), la liste des
    postes à pourvoir après application d'éventuelles mesures de dégradation.
    Retourne aussi la liste des libellés de jour ('lundi', 'mardi', ...)."""
    effectifs_reduits = effectifs_reduits or {}
    postes_par_jour: Dict[int, List[config.PosteConfig]] = {}
    jours_labels: List[str] = []

    for d, date in enumerate(jours):
        label = jour_semaine_fr(date)
        jours_labels.append(label)
        postes = config.get_postes_du_jour(label, est_ferie(date))
        postes_filtres = []
        for p in postes:
            if p.code in postes_retires:
                continue
            if p.code in effectifs_reduits:
                p = dataclasses.replace(p, effectif=effectifs_reduits[p.code])
            postes_filtres.append(p)
        postes_par_jour[d] = postes_filtres

    return postes_par_jour, jours_labels


def creer_variables(
    model: cp_model.CpModel,
    medecins,
    jours: List[datetime.date],
    postes_par_jour: Dict[int, List[config.PosteConfig]],
    ctx: Contexte,
) -> VariableDict:
    x: VariableDict = {}
    for d, postes in postes_par_jour.items():
        date = jours[d]
        for m in medecins:
            if date in ctx.indispo_par_medecin.get(m.id, set()):
                continue
            for p in postes:
                x[(m.id, d, p.code)] = model.NewBoolVar("x_m{}_d{}_{}".format(m.id, d, p.code))
    return x


def build_and_solve(
    medecins,
    jours: List[datetime.date],
    jours_labels: List[str],
    postes_par_jour: Dict[int, List[config.PosteConfig]],
    ctx: Contexte,
):
    model = cp_model.CpModel()
    x = creer_variables(model, medecins, jours, postes_par_jour, ctx)
    titulaires_secteur = constraints.add_all(model, x, medecins, jours_labels, postes_par_jour, ctx)
    objective.add_equite(model, x, medecins, jours_labels, postes_par_jour, ctx, titulaires_secteur)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = TEMPS_MAX_RESOLUTION_S
    solver.parameters.num_search_workers = 8
    status = solver.Solve(model)
    return status, solver, x


def extraire_affectations(
    solver: cp_model.CpSolver, x: VariableDict, jours: List[datetime.date]
) -> List[Tuple[datetime.date, str, int]]:
    resultat = []
    for (m_id, d, poste_code), var in x.items():
        if solver.Value(var) == 1:
            resultat.append((jours[d], poste_code, m_id))
    return resultat


def statut_est_faisable(status: int) -> bool:
    return status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
