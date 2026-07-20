"""
Configuration centrale de l'application.

TOUT paramètre métier (horaires de poste, limites horaires, règles de rotation,
ordre de dégradation) doit vivre ici et nulle part ailleurs. Le code du solver,
de l'UI et de la base de données lisent ces constantes, ils ne codent jamais un
horaire ou un seuil en dur.

Pour ajouter/modifier un poste, une pause ou un seuil : on modifie ce fichier,
on ne touche pas au reste du code.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PosteConfig:
    """Définition d'un poste fixe à pourvoir."""

    code: str
    label: str
    heure_debut: str  # "HH:MM"
    heure_fin: str  # "HH:MM", peut être < heure_debut si le poste chevauche minuit
    duree_h: int
    effectif: int  # nombre de médecins requis simultanément sur ce poste
    est_nuit: bool = False  # True pour les gardes 20h-8h


# ---------------------------------------------------------------------------
# 1. POSTES FIXES À POURVOIR (LA DEMANDE)
# ---------------------------------------------------------------------------

POSTES_SEMAINE: list[PosteConfig] = [
    PosteConfig("POLY_MATIN", "Polyclinique 8h-18h", "08:00", "18:00", 10, 1),
    PosteConfig("POLY_JOURNEE", "Polyclinique 10h-20h", "10:00", "20:00", 10, 1),
    PosteConfig("APRES_MIDI", "Bridge", "13:00", "22:00", 9, 1),
    # Secteurs de jour : 3 postes DISTINCTS (et non plus un seul poste à
    # effectif 3) pour donner à chaque secteur une identité propre, condition
    # nécessaire à la contrainte de continuité/stabilité hebdomadaire (cf.
    # app.solver.constraints.add_stabilite_secteur_hebdomadaire) : le solveur
    # doit pouvoir raisonner sur "le même médecin sur le Secteur 1" d'un jour
    # à l'autre, ce qu'un pool interchangeable de 3 slots ne permettait pas.
    PosteConfig("SECTEUR_1", "Secteur 1", "08:00", "18:00", 10, 1),
    PosteConfig("SECTEUR_2", "Secteur 2", "08:00", "18:00", 10, 1),
    PosteConfig("SECTEUR_3", "Secteur 3", "08:00", "18:00", 10, 1),
    PosteConfig("GARDE_NUIT", "Garde de Nuit (Service)", "20:00", "08:00", 12, 1, est_nuit=True),
]

# Liste des codes de secteur, dans l'ordre d'affichage. Référencée par le
# solver (contrainte de stabilité + objectif de continuité) et par l'UI
# (grille, légende) plutôt que rechargée en dur à chaque endroit.
POSTES_SECTEURS: list[str] = ["SECTEUR_1", "SECTEUR_2", "SECTEUR_3"]

POSTES_SAMEDI: list[PosteConfig] = [
    PosteConfig("SAM_JOUR_COURT", "Jour court", "09:00", "17:00", 8, 1),
    PosteConfig("SAM_JOUR_LONG", "Jour long", "08:00", "20:00", 12, 1),
    PosteConfig("GARDE_NUIT", "Garde de Nuit", "20:00", "08:00", 12, 1, est_nuit=True),
]

POSTES_DIMANCHE: list[PosteConfig] = [
    PosteConfig("DIM_JOUR_UNIQUE", "Jour unique", "08:00", "20:00", 12, 1),
    PosteConfig("GARDE_NUIT", "Garde de Nuit", "20:00", "08:00", 12, 1, est_nuit=True),
]

# Régime appliqué à un jour férié tombant en semaine (lundi-vendredi).
# "samedi" ou "dimanche" -> détermine quelle liste de postes ci-dessus s'applique.
REGIME_FERIE = "samedi"

# ---------------------------------------------------------------------------
# 2. CONTRAINTES STRICTES (HARD CONSTRAINTS)
# ---------------------------------------------------------------------------

LIMITES = {
    "max_heures_semaine": 50,  # lundi -> dimanche, par médecin
}

# ---------------------------------------------------------------------------
# 3. MÉMOIRE GLISSANTE
# ---------------------------------------------------------------------------

MEMOIRE_JOURS = 30  # historique relu avant chaque génération

# ---------------------------------------------------------------------------
# 4. RÈGLES DE ROTATION / ÉQUITÉ / CONTINUITÉ
# ---------------------------------------------------------------------------

REGLES_ROTATION = {
    # Blocs de nuit : jamais de garde isolée, uniquement ces blocs complets.
    "blocs_nuit": {
        "semaine": ["mardi", "mercredi", "jeudi"],
        "weekend_prolonge": ["vendredi", "samedi", "dimanche", "lundi"],
    },
    # Un médecin qui termine le bloc week-end prolongé (fin mardi 08h) ne travaille
    # pas le mardi en journée, et bénéficie d'au moins ce nombre de jours de repos
    # consécutifs immédiatement après (le mardi inclus).
    "repos_min_jours_apres_bloc_weekend": 3,
    # Passage sur un Secteur : pas de semaine isolée, pas de fractionnement.
    "service_duree_min_semaines": 2,
    "service_duree_max_semaines": 8,  # 1-2 mois
}

# ---------------------------------------------------------------------------
# 4bis. CONTINUITÉ DES SOINS SUR LES SECTEURS (STABILITÉ)
# ---------------------------------------------------------------------------
# - Contrainte DURE (hard) : sur une même semaine calendaire (lundi-vendredi),
#   un secteur donné (Secteur 1/2/3) ne peut être attribué qu'à un seul et
#   unique médecin. Exception tolérée uniquement le(s) jour(s) où ce médecin
#   référent est en Garde de Nuit ou en congé ce jour précis (cf.
#   app.solver.constraints.add_stabilite_secteur_hebdomadaire).
# - Objectif PRIORITAIRE (soft) du solveur : au-delà de la semaine, maximiser
#   la probabilité que le même médecin reste sur le même secteur plusieurs
#   semaines d'affilée (2-3 semaines, voire tout le mois), quand congés et
#   gardes le permettent. POIDS_CONTINUITE_SECTEUR pondère fortement ce bonus
#   dans la fonction objectif (cf. app.solver.objective.add_equite), pour
#   qu'il prenne le pas sur l'objectif d'équité en cas d'arbitrage.
POIDS_CONTINUITE_SECTEUR = 1000

# ---------------------------------------------------------------------------
# 5. GESTION DE LA PÉNURIE (RÈGLES DE DÉGRADATION)
# ---------------------------------------------------------------------------
# Ordre strict dans lequel les postes sont sacrifiés si la semaine est
# mathématiquement infaisable. Chaque étape est appliquée cumulativement.

DEGRADATION_ETAPE_1 = {
    "id": "retirer_apres_midi",
    "description": "Retirer le poste Bridge (13h-22h) de la semaine",
    "poste_code": "APRES_MIDI",
}

DEGRADATION_ETAPE_2 = {
    "id": "retirer_secteur_3",
    "description": "Retirer le Secteur 3 (fermeture temporaire faute d'effectif)",
    "poste_code": "SECTEUR_3",
}

ORDRE_DEGRADATION = [DEGRADATION_ETAPE_1, DEGRADATION_ETAPE_2]

# ---------------------------------------------------------------------------
# 6. JOURS FÉRIÉS
# ---------------------------------------------------------------------------

PAYS_FERIES = "CH"
SOUS_REGION_FERIES = "VD"  # Canton de Vaud (région Yverdon / Sainte-Croix)


def get_postes_du_jour(jour_semaine: str, est_ferie: bool) -> list[PosteConfig]:
    """Retourne la liste des postes à pourvoir pour un jour donné.

    jour_semaine: 'lundi', 'mardi', ..., 'dimanche'
    est_ferie: True si le jour est un jour férié (CH-VD)
    """
    if est_ferie and jour_semaine not in ("samedi", "dimanche"):
        jour_semaine = REGIME_FERIE

    if jour_semaine == "samedi":
        return POSTES_SAMEDI
    if jour_semaine == "dimanche":
        return POSTES_DIMANCHE
    return POSTES_SEMAINE
