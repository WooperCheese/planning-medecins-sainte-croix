"""
Calcul des heures (prévues + supplémentaires) par médecin et génération de
l'export Excel pour la paie — portail RH.

Séparé de l'UI (comme app/auth/comptes.py) pour rester testable sans
Streamlit. Le calcul des heures prévues réutilise la config des postes
existante (app/config.py) : aucune nouvelle source de vérité sur les durées.

Cf. docs/superpowers/specs/2026-07-21-portail-rh-design.md.

100% compatible Python 3.9 : Optional[...] partout, jamais de `X | None`.
"""

from __future__ import annotations

import datetime
import io
from typing import Dict, List

import pandas as pd
from sqlalchemy.orm import Session

from app.config import POSTES_DIMANCHE, POSTES_SAMEDI, POSTES_SEMAINE
from app.db.models import Affectation, HeureSup, Medecin


def _duree_par_code_poste() -> Dict[str, int]:
    """Fusionne les trois listes de postes (semaine/samedi/dimanche) en un
    dictionnaire code -> duree_h. Les codes partagés entre listes (ex :
    GARDE_NUIT) ont la même durée dans les trois — un simple update suffit,
    pas besoin de vérifier la cohérence à l'exécution."""
    durees: Dict[str, int] = {}
    for postes in (POSTES_SEMAINE, POSTES_SAMEDI, POSTES_DIMANCHE):
        for p in postes:
            durees[p.code] = p.duree_h
    return durees


def heures_prevues_par_medecin(
    session: Session,
    medecins: List[Medecin],
    premier_jour: datetime.date,
    dernier_jour: datetime.date,
) -> Dict[int, float]:
    """Somme, pour chaque médecin, la durée des affectations planifiées sur
    la période [premier_jour, dernier_jour] (bornes incluses)."""
    durees_par_code = _duree_par_code_poste()
    totaux = {m.id: 0.0 for m in medecins}
    ids_medecins = set(totaux.keys())

    affectations = (
        session.query(Affectation)
        .filter(Affectation.date >= premier_jour, Affectation.date <= dernier_jour)
        .all()
    )
    for a in affectations:
        if a.medecin_id not in ids_medecins:
            continue
        totaux[a.medecin_id] += durees_par_code[a.poste_code]

    return totaux


def heures_sup_par_medecin(
    session: Session,
    medecins: List[Medecin],
    premier_jour: datetime.date,
    dernier_jour: datetime.date,
) -> Dict[int, float]:
    """Somme, pour chaque médecin, les heures supplémentaires déclarées sur
    la période [premier_jour, dernier_jour] (bornes incluses)."""
    totaux = {m.id: 0.0 for m in medecins}
    ids_medecins = set(totaux.keys())

    declarations = (
        session.query(HeureSup)
        .filter(HeureSup.date >= premier_jour, HeureSup.date <= dernier_jour)
        .all()
    )
    for h in declarations:
        if h.medecin_id not in ids_medecins:
            continue
        totaux[h.medecin_id] += h.nb_heures

    return totaux


def generer_export_excel(
    medecins: List[Medecin],
    heures_prevues: Dict[int, float],
    heures_sup: Dict[int, float],
) -> bytes:
    """Construit un export .xlsx (une ligne par médecin + une ligne total
    général) en mémoire, prêt à être passé à st.download_button."""
    lignes = []
    for m in sorted(medecins, key=lambda m: m.nom_complet()):
        prevues = heures_prevues.get(m.id, 0.0)
        sup = heures_sup.get(m.id, 0.0)
        lignes.append(
            {
                "Médecin": m.nom_complet(),
                "Heures prévues": prevues,
                "Heures sup": sup,
                "Total": prevues + sup,
            }
        )

    df = pd.DataFrame(lignes, columns=["Médecin", "Heures prévues", "Heures sup", "Total"])
    df.loc[len(df)] = {
        "Médecin": "TOTAL",
        "Heures prévues": df["Heures prévues"].sum(),
        "Heures sup": df["Heures sup"].sum(),
        "Total": df["Total"].sum(),
    }

    tampon = io.BytesIO()
    with pd.ExcelWriter(tampon, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Paie")
    return tampon.getvalue()
