"""
Garde-fou appliqué avant d'enregistrer une modification manuelle du planning
(page Planning, bouton "Valider et enregistrer les modifications").

Ne revérifie que les contraintes dures explicitement demandées pour cette
vérification rapide : pas de chevauchement de poste pour un même médecin le
même jour, et pas de dépassement des 50h/semaine. Les autres règles (blocs de
nuit, continuité du service, équité...) restent du ressort du moteur CP-SAT
lors de la génération automatique ; un ajustement manuel ponctuel n'a pas à
les revalider intégralement.

100% compatible Python 3.9 : Optional[...] partout, jamais de `X | None`.
"""

from __future__ import annotations

import datetime
from typing import Dict, List, Optional, Tuple

from app.config import LIMITES, get_postes_du_jour
from app.solver.calendar_ch import est_ferie, jour_semaine_fr


def _duree_poste(date: datetime.date, poste_code: str) -> int:
    label = jour_semaine_fr(date)
    for p in get_postes_du_jour(label, est_ferie(date)):
        if p.code == poste_code:
            return p.duree_h
    return 0


def valider_grille_manuelle(
    affectations: List[Tuple[datetime.date, str, Optional[int]]],
    noms_par_medecin_id: Dict[int, str],
) -> List[str]:
    """affectations : liste de (date, poste_code, medecin_id ou None si case vide).

    Retourne la liste des messages d'erreur (liste vide = tout est correct).
    """
    erreurs: List[str] = []

    # --- 1. Chevauchement : un médecin ne peut avoir qu'un seul poste par jour.
    postes_par_medecin_jour: Dict[Tuple[int, datetime.date], List[str]] = {}
    for date, poste_code, medecin_id in affectations:
        if medecin_id is None:
            continue
        postes_par_medecin_jour.setdefault((medecin_id, date), []).append(poste_code)

    for (medecin_id, date), postes in postes_par_medecin_jour.items():
        if len(postes) > 1:
            nom = noms_par_medecin_id.get(medecin_id, "médecin #{}".format(medecin_id))
            erreurs.append(
                "{} est affecté à {} postes le {} ({}) : un seul poste par jour est "
                "autorisé.".format(nom, len(postes), date.strftime("%d.%m.%Y"), ", ".join(postes))
            )

    # --- 2. Max 50h / semaine par médecin.
    heures_par_medecin: Dict[int, int] = {}
    for date, poste_code, medecin_id in affectations:
        if medecin_id is None:
            continue
        heures_par_medecin[medecin_id] = heures_par_medecin.get(medecin_id, 0) + _duree_poste(date, poste_code)

    for medecin_id, heures in heures_par_medecin.items():
        if heures > LIMITES["max_heures_semaine"]:
            nom = noms_par_medecin_id.get(medecin_id, "médecin #{}".format(medecin_id))
            erreurs.append(
                "{} totalise {}h cette semaine, au-delà de la limite stricte de "
                "{}h.".format(nom, heures, LIMITES["max_heures_semaine"])
            )

    return erreurs
