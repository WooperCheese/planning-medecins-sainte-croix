"""
Boucle de dégradation : si la période (le mois) est mathématiquement
infaisable avec la demande complète, on sacrifie des postes dans l'ordre
strict défini par app.config.ORDRE_DEGRADATION, jusqu'à trouver une solution
faisable (ou épuiser les étapes de dégradation disponibles).

Chaque sacrifice appliqué est retourné pour être loggé et affiché en alerte
rouge à l'admin — rien n'est sacrifié silencieusement.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field

from app import config
from app.solver import engine
from app.solver.history import Contexte


@dataclass
class ResultatGeneration:
    faisable: bool
    affectations: list[tuple[datetime.date, str, int]]
    postes_sacrifies: list[str] = field(default_factory=list)
    message: str = ""


def resoudre_avec_degradation(medecins, jours: list[datetime.date], ctx: Contexte) -> ResultatGeneration:
    postes_retires: set[str] = set()
    effectifs_reduits: dict[str, int] = {}
    sacrifices_appliques: list[str] = []

    # Tentative 0 : demande complète, sans aucune dégradation.
    etapes = [None] + list(config.ORDRE_DEGRADATION)

    for etape in etapes:
        if etape is not None:
            if "nouvel_effectif" in etape:
                effectifs_reduits[etape["poste_code"]] = etape["nouvel_effectif"]
            else:
                postes_retires.add(etape["poste_code"])
            sacrifices_appliques.append(etape["description"])

        postes_par_jour, jours_labels = engine.calculer_postes_periode(
            jours, frozenset(postes_retires), effectifs_reduits
        )
        status, solver, x = engine.build_and_solve(medecins, jours, jours_labels, postes_par_jour, ctx)

        if engine.statut_est_faisable(status):
            affectations = engine.extraire_affectations(solver, x, jours)
            return ResultatGeneration(
                faisable=True,
                affectations=affectations,
                postes_sacrifies=list(sacrifices_appliques),
                message=(
                    "Planning généré sans dégradation."
                    if not sacrifices_appliques
                    else "Planning généré avec dégradation : " + " ; ".join(sacrifices_appliques)
                ),
            )

    return ResultatGeneration(
        faisable=False,
        affectations=[],
        postes_sacrifies=list(sacrifices_appliques),
        message=(
            "Aucune solution trouvée même après application de toutes les mesures de "
            "dégradation disponibles. Intervention manuelle de l'admin requise "
            "(effectif probablement insuffisant sur ce mois)."
        ),
    )
