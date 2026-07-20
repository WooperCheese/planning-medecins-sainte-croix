"""
Calendrier dynamique des jours fériés suisses (canton de Vaud).

Isole la dépendance au package `holidays` : si la logique de fériés doit
changer (autre canton, jours spéciaux de l'hôpital), c'est ce module qu'on
modifie, rien d'autre.
"""

from __future__ import annotations

import datetime
from typing import Optional

import holidays

from app.config import PAYS_FERIES, SOUS_REGION_FERIES

JOURS_SEMAINE_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]

_feries_cache: dict[int, holidays.HolidayBase] = {}


def _get_feries_annee(annee: int) -> holidays.HolidayBase:
    if annee not in _feries_cache:
        _feries_cache[annee] = holidays.country_holidays(
            PAYS_FERIES, subdiv=SOUS_REGION_FERIES, years=annee
        )
    return _feries_cache[annee]


def est_ferie(date: datetime.date) -> bool:
    return date in _get_feries_annee(date.year)


def nom_ferie(date: datetime.date) -> Optional[str]:
    feries = _get_feries_annee(date.year)
    return feries.get(date)


def jour_semaine_fr(date: datetime.date) -> str:
    """Retourne 'lundi', 'mardi', ... pour une date donnée."""
    return JOURS_SEMAINE_FR[date.weekday()]
