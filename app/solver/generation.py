"""
Point d'entrée unique appelé par l'UI admin : génère le planning d'un mois
civil complet et persiste le résultat en base (Affectation + GenerationLog),
et permet de réinitialiser complètement un mois (utilisé par le bouton rouge
"Réinitialiser ce mois" en cas de conflit de clés).

C'est le seul module du package `solver` qui touche à la session SQLAlchemy :
engine.py, constraints.py, objective.py, degradation.py et history.py restent
purs / testables sans base de données réelle (hormis history.py qui lit la
session en lecture seule, cf. ses tests avec une DB SQLite en mémoire).

100% compatible Python 3.9 : Optional[...] partout, jamais de `X | None`.
"""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.db.models import Affectation, GenerationLog, StatutAffectation
from app.solver import engine
from app.solver.degradation import ResultatGeneration, resoudre_avec_degradation
from app.solver.history import charger_contexte


def generer_mois(session: Session, annee: int, mois: int, admin_username: str) -> ResultatGeneration:
    """Génère (ou régénère) le planning du mois civil `mois`/`annee` complet.

    La colonne GenerationLog.semaine_debut est réutilisée telle quelle (pas de
    migration de schéma nécessaire) pour stocker le premier jour du mois généré.

    Les affectations générées automatiquement (statut GENERE) pour ce mois
    sont remplacées ; celles modifiées manuellement par l'admin (statut
    MODIFIE_MANUELLEMENT) sont conservées. Pour éviter un conflit avec la
    contrainte UNIQUE (date, poste_code, medecin_id) si le solveur propose par
    coïncidence exactement le même triplet qu'une modification manuelle déjà
    en base, ces triplets sont détectés et simplement ignorés à l'insertion
    (l'affectation manuelle existante fait déjà foi). En cas de conflit plus
    large, le bouton "Réinitialiser ce mois" (cf. reinitialiser_mois) reste le
    filet de sécurité : il vide tout le mois avant une nouvelle génération.
    """
    jours = engine.jours_du_mois(annee, mois)
    premier_jour = jours[0]
    dernier_jour = jours[-1]

    ctx = charger_contexte(session, premier_jour, dernier_jour)
    resultat = resoudre_avec_degradation(ctx.medecins, jours, ctx)

    if resultat.faisable:
        # On retire les anciennes affectations générées automatiquement pour ce
        # mois avant d'écrire la nouvelle solution (idempotent), mais on ne
        # touche pas à celles déjà modifiées manuellement par l'admin.
        (
            session.query(Affectation)
            .filter(
                Affectation.date >= premier_jour,
                Affectation.date <= dernier_jour,
                Affectation.statut == StatutAffectation.GENERE.value,
            )
            .delete(synchronize_session=False)
        )
        session.flush()

        # Triplets encore présents en base pour ce mois (uniquement les
        # modifications manuelles à ce stade) : à ne jamais réinsérer en double.
        triplets_existants = {
            (a.date, a.poste_code, a.medecin_id)
            for a in session.query(Affectation)
            .filter(Affectation.date >= premier_jour, Affectation.date <= dernier_jour)
            .all()
        }

        for date, poste_code, medecin_id in resultat.affectations:
            if (date, poste_code, medecin_id) in triplets_existants:
                continue  # déjà couvert par une modification manuelle existante
            session.add(
                Affectation(
                    date=date,
                    poste_code=poste_code,
                    medecin_id=medecin_id,
                    statut=StatutAffectation.GENERE.value,
                    degrade=bool(resultat.postes_sacrifies),
                )
            )

    session.add(
        GenerationLog(
            semaine_debut=premier_jour,
            admin_username=admin_username,
            postes_sacrifies_json=json.dumps(resultat.postes_sacrifies, ensure_ascii=False),
            faisable=resultat.faisable,
        )
    )

    return resultat


def reinitialiser_mois(session: Session, annee: int, mois: int) -> int:
    """Supprime DÉFINITIVEMENT toutes les affectations (générées ET modifiées
    manuellement) du mois civil `mois`/`annee`. Utilisé par le bouton rouge
    "Réinitialiser ce mois" de la page Planning, pour repartir d'une base
    propre quand une régénération est bloquée par un conflit de clés.

    Retourne le nombre de lignes supprimées. L'historique de génération
    (GenerationLog) n'est volontairement pas touché, pour garder une trace
    d'audit de ce qui s'est passé.
    """
    jours = engine.jours_du_mois(annee, mois)
    premier_jour, dernier_jour = jours[0], jours[-1]
    return (
        session.query(Affectation)
        .filter(Affectation.date >= premier_jour, Affectation.date <= dernier_jour)
        .delete(synchronize_session=False)
    )
