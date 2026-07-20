"""
Fonction objectif combinée du solveur :

1. Équité : minimiser l'écart entre le médecin le plus et le moins sollicité
   en nuits + jours de week-end, en tenant compte de l'historique (mémoire
   glissante) et de la période en cours de génération.
2. Continuité des Secteurs (objectif PRIORITAIRE, cf. app.config) : maximiser
   le nombre de fois où le même médecin reste titulaire d'un même secteur
   (Secteur 1/2/3) d'une semaine calendaire à la suivante, y compris à cheval
   sur la frontière avec le mois précédent. S'appuie sur les variables
   "titulaire" construites par
   app.solver.constraints.add_stabilite_secteur_hebdomadaire.

CP-SAT n'accepte qu'un seul appel Minimize/Maximize par modèle : les deux
objectifs sont donc combinés en une seule expression linéaire, avec un poids
fort (POIDS_CONTINUITE_SECTEUR) sur la continuité pour qu'elle prenne le pas
sur l'équité en cas d'arbitrage, conformément à la consigne métier.
"""

from __future__ import annotations

from typing import Optional

from ortools.sat.python import cp_model

from app.config import POIDS_CONTINUITE_SECTEUR
from app.solver.history import Contexte

JOURS_WEEKEND = {"samedi", "dimanche"}


def add_equite(
    model: cp_model.CpModel,
    x: dict,
    medecins,
    jours_labels: list[str],
    postes_par_jour: dict[int, list],
    ctx: Contexte,
    titulaires_secteur: Optional[dict] = None,
) -> None:
    totaux = []
    borne_max = 200  # large mais borné, requis par CP-SAT pour les IntVar

    for m in medecins:
        contribution_semaine = []
        for d, postes in postes_par_jour.items():
            jour_label = jours_labels[d]
            for p in postes:
                if (m.id, d, p.code) not in x:
                    continue
                compte_pour_equite = p.est_nuit or jour_label in JOURS_WEEKEND
                if compte_pour_equite:
                    contribution_semaine.append(x[(m.id, d, p.code)])

        base = ctx.score_equite.get(m.id, 0)
        total_m = model.NewIntVar(0, borne_max, f"total_equite_{m.id}")
        if contribution_semaine:
            model.Add(total_m == base + sum(contribution_semaine))
        else:
            model.Add(total_m == base)
        totaux.append(total_m)

    if not totaux:
        return

    maximum = model.NewIntVar(0, borne_max, "max_equite")
    minimum = model.NewIntVar(0, borne_max, "min_equite")
    model.AddMaxEquality(maximum, totaux)
    model.AddMinEquality(minimum, totaux)
    objectif = maximum - minimum

    continuite_terms = _construire_bonus_continuite_secteur(model, titulaires_secteur, ctx)
    if continuite_terms:
        objectif = objectif - POIDS_CONTINUITE_SECTEUR * sum(continuite_terms)

    model.Minimize(objectif)


def _construire_bonus_continuite_secteur(
    model: cp_model.CpModel,
    titulaires_secteur,
    ctx: Contexte,
) -> list:
    """Construit les variables booléennes "continu_..." qui valent 1 quand le
    même médecin est titulaire d'un secteur sur deux semaines consécutives
    (dans l'horizon généré), plus un terme supplémentaire pour la continuité
    avec le titulaire de la semaine précédant le début du mois (ctx), afin que
    le bonus ne s'arrête pas artificiellement à la frontière du mois."""
    if not titulaires_secteur:
        return []

    termes = []

    # 1. Continuité intra-horizon : semaine N -> semaine N+1, par secteur.
    par_secteur: dict = {}
    for (num_semaine, secteur_code), titulaire_map in titulaires_secteur.items():
        par_secteur.setdefault(secteur_code, {})[num_semaine] = titulaire_map

    for secteur_code, semaines in par_secteur.items():
        numeros = sorted(semaines.keys())
        for n1, n2 in zip(numeros, numeros[1:]):
            t1, t2 = semaines[n1], semaines[n2]
            communs = set(t1.keys()) & set(t2.keys())
            for m_id in communs:
                continu = model.NewBoolVar("continu_{}_{}_{}_m{}".format(secteur_code, n1, n2, m_id))
                model.Add(continu <= t1[m_id])
                model.Add(continu <= t2[m_id])
                model.Add(continu >= t1[m_id] + t2[m_id] - 1)
                termes.append(continu)

    # 2. Continuité avec le mois précédent : bonus direct si le titulaire de
    # la toute première semaine générée est le même que celui de la dernière
    # semaine connue avant le début de la période (cf. history.py).
    if ctx is not None:
        for secteur_code, semaines in par_secteur.items():
            if 0 not in semaines:
                continue
            titulaire_prec = ctx.titulaire_secteur_semaine_precedente.get(secteur_code)
            if titulaire_prec is not None and titulaire_prec in semaines[0]:
                termes.append(semaines[0][titulaire_prec])

    return termes
