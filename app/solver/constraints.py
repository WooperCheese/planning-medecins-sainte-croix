"""
Contraintes dures (hard constraints) du modèle CP-SAT.

Chaque fonction ajoute un type de règle au modèle. Rien ici ne connaît les
horaires ou seuils en dur : tout vient de app.config ou du contexte historique
(app.solver.history.Contexte). Toutes les fonctions travaillent sur un horizon
de longueur quelconque (jours_labels peut représenter une semaine ou un mois
civil complet) : les blocs de nuit et les semaines de 50h sont retrouvés par
scan positionnel plutôt que par index fixe.

100% compatible Python 3.9 : Optional[...] partout, jamais de `X | None`.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from ortools.sat.python import cp_model

from app.config import LIMITES, POSTES_SECTEURS, REGLES_ROTATION
from app.solver.history import Contexte

BLOC_SEMAINE_LABELS: List[str] = REGLES_ROTATION["blocs_nuit"]["semaine"]  # mardi, mercredi, jeudi
BLOC_WEEKEND_LABELS: List[str] = ["vendredi", "samedi", "dimanche", "lundi"]
REPOS_MIN_JOURS = REGLES_ROTATION["repos_min_jours_apres_bloc_weekend"]
SERVICE_MIN_SEMAINES = REGLES_ROTATION["service_duree_min_semaines"]
SERVICE_MAX_SEMAINES = REGLES_ROTATION["service_duree_max_semaines"]

VariableDict = Dict[Tuple[int, int, str], cp_model.IntVar]
# Titulaire d'un secteur pour une semaine donnée : {(num_semaine, poste_code): {medecin_id: BoolVar}}
TitulaireSecteurDict = Dict[Tuple[int, str], Dict[int, cp_model.IntVar]]


def _grouper_semaines(jours_labels: List[str]) -> List[List[int]]:
    """Regroupe les indices de jours de l'horizon en semaines calendaires
    réelles (chaque nouveau "lundi" démarre un groupe). La toute première
    semaine peut être partielle si l'horizon ne démarre pas un lundi.
    Factorisé ici car réutilisé par add_max_heures_semaine ET par
    add_stabilite_secteur_hebdomadaire (les deux ont besoin des mêmes
    frontières de semaine calendaire)."""
    groupes: List[List[int]] = []
    courant: List[int] = []
    for i, label in enumerate(jours_labels):
        if label == "lundi" and courant:
            groupes.append(courant)
            courant = []
        courant.append(i)
    if courant:
        groupes.append(courant)
    return groupes


def add_couverture(model: cp_model.CpModel, x: VariableDict, medecins, jours_labels, postes_par_jour) -> None:
    """Chaque poste requis est couvert par exactement l'effectif demandé."""
    for d, postes in postes_par_jour.items():
        for poste in postes:
            vars_du_poste = [x[(m.id, d, poste.code)] for m in medecins if (m.id, d, poste.code) in x]
            model.Add(sum(vars_du_poste) == poste.effectif)


def add_unicite_par_jour(model: cp_model.CpModel, x: VariableDict, medecins, jours_labels, postes_par_jour) -> None:
    """Un médecin ne peut être affecté qu'à un seul poste par jour."""
    for m in medecins:
        for d in postes_par_jour:
            vars_du_jour = [x[(m.id, d, p.code)] for p in postes_par_jour[d] if (m.id, d, p.code) in x]
            if vars_du_jour:
                model.Add(sum(vars_du_jour) <= 1)


def add_blocs_nuit(model: cp_model.CpModel, x: VariableDict, medecins, jours_labels, postes_par_jour) -> None:
    """Les gardes de nuit ne sont jamais isolées : bloc mar-mer-jeu, et bloc
    ven-sam-dim-lun. Fonctionne sur un horizon de longueur quelconque : on
    cherche chaque occurrence d'un début de bloc dans jours_labels et on lie
    les jours suivants tant qu'ils restent dans l'horizon (un bloc tronqué en
    fin d'horizon est lié partiellement ; sa continuation le mois suivant est
    gérée par add_continuite_bloc_debut_mois via l'historique)."""
    n = len(jours_labels)
    for pattern in (BLOC_SEMAINE_LABELS, BLOC_WEEKEND_LABELS):
        premier_label = pattern[0]
        for i, label in enumerate(jours_labels):
            if label != premier_label:
                continue
            indices_bloc = [i]
            for offset, label_attendu in enumerate(pattern[1:], start=1):
                j = i + offset
                if j >= n or jours_labels[j] != label_attendu:
                    break
                indices_bloc.append(j)
            for m in medecins:
                vars_bloc = [
                    x[(m.id, d, "GARDE_NUIT")] for d in indices_bloc if (m.id, d, "GARDE_NUIT") in x
                ]
                for a, b in zip(vars_bloc, vars_bloc[1:]):
                    model.Add(a == b)


def add_continuite_bloc_debut_mois(
    model: cp_model.CpModel, x: VariableDict, medecins, jours_labels, ctx: Contexte
) -> None:
    """Force la continuation, en tout début de période, d'un bloc de nuit
    entamé le mois précédent (cf. history._bloc_a_forcer_debut_periode). Si
    c'est la fin du bloc week-end prolongé, impose aussi le repos qui suit.
    Si aucun historique cohérent (bootstrap), ne fait rien : les premiers
    jours restent des slots libres pour cette génération."""
    if ctx.medecin_bloc_a_forcer is None or not ctx.jours_bloc_a_forcer:
        return

    m_id = ctx.medecin_bloc_a_forcer
    indices = list(range(len(ctx.jours_bloc_a_forcer)))  # ces jours sont toujours en tout début d'horizon

    for d in indices:
        if (m_id, d, "GARDE_NUIT") not in x:
            return  # médecin devenu indisponible entre-temps : cas limite, on abandonne la continuité
        model.Add(x[(m_id, d, "GARDE_NUIT")] == 1)
        for other in medecins:
            if other.id != m_id and (other.id, d, "GARDE_NUIT") in x:
                model.Add(x[(other.id, d, "GARDE_NUIT")] == 0)

    if ctx.bloc_a_forcer_est_weekend:
        debut_repos = indices[-1] + 1
        nb_jours_repos = REPOS_MIN_JOURS - 1
        for jour_idx in range(debut_repos, min(debut_repos + nb_jours_repos, len(jours_labels))):
            for poste_code_jour in list({p for (mid, d, p) in x if mid == m_id and d == jour_idx}):
                model.Add(x[(m_id, jour_idx, poste_code_jour)] == 0)


def add_jumelage_weekend(model: cp_model.CpModel, x: VariableDict, medecins, jours_labels) -> None:
    """Règle stricte de jumelage week-end : le médecin affecté à la Journée
    Longue du samedi (SAM_JOUR_LONG, 8h-20h) doit être le même que celui
    affecté au Jour unique du dimanche (DIM_JOUR_UNIQUE, 8h-20h) qui suit."""
    n = len(jours_labels)
    for i, label in enumerate(jours_labels):
        if label != "samedi" or i + 1 >= n or jours_labels[i + 1] != "dimanche":
            continue
        for m in medecins:
            var_sam = x.get((m.id, i, "SAM_JOUR_LONG"))
            var_dim = x.get((m.id, i + 1, "DIM_JOUR_UNIQUE"))
            if var_sam is not None and var_dim is not None:
                model.Add(var_sam == var_dim)
            elif var_sam is not None:
                model.Add(var_sam == 0)  # ne peut pas faire le samedi seul sans le dimanche
            elif var_dim is not None:
                model.Add(var_dim == 0)  # ne peut pas faire le dimanche seul sans le samedi


def add_max_heures_semaine(
    model: cp_model.CpModel,
    x: VariableDict,
    medecins,
    jours_labels,
    postes_par_jour,
    heures_semaine_partielle_precedente,
) -> None:
    """Max 50h par semaine calendaire (lundi-dimanche). L'horizon est regroupé
    en semaines réelles (chaque nouveau "lundi" démarre un groupe) ; la toute
    première semaine, éventuellement partielle si l'horizon ne démarre pas un
    lundi, reçoit en plus les heures déjà travaillées le mois précédent sur
    cette même semaine (cf. history._heures_semaine_partielle_precedente)."""
    groupes = _grouper_semaines(jours_labels)

    for m in medecins:
        for num_groupe, indices in enumerate(groupes):
            total = []
            for d in indices:
                for p in postes_par_jour.get(d, []):
                    if (m.id, d, p.code) in x:
                        total.append(x[(m.id, d, p.code)] * p.duree_h)
            offset = heures_semaine_partielle_precedente.get(m.id, 0) if num_groupe == 0 else 0
            if total or offset:
                model.Add(sum(total) + offset <= LIMITES["max_heures_semaine"])


def add_continuite_secteurs(
    model: cp_model.CpModel, x: VariableDict, medecins, jours_labels, postes_par_jour, ctx: Contexte
) -> None:
    """Pas de semaine isolée sur les Secteurs (durée min), pas de roulement trop
    long (durée max). Porte sur l'activité "secteur" en général (Secteur 1, 2
    ou 3 confondus) : c'est le suivi historique de streak qui ne distingue pas
    le secteur précis. La stabilité PAR secteur (même médecin sur le MÊME
    secteur) est une règle séparée, cf. add_stabilite_secteur_hebdomadaire."""
    for m in medecins:
        vars_service = [
            x[(m.id, d, code)]
            for d in postes_par_jour
            for code in POSTES_SECTEURS
            if (m.id, d, code) in x
        ]
        if not vars_service:
            continue
        streak = ctx.service_streak_semaines.get(m.id, 0)
        if 0 < streak < SERVICE_MIN_SEMAINES:
            model.Add(sum(vars_service) >= 1)
        elif streak >= SERVICE_MAX_SEMAINES:
            model.Add(sum(vars_service) == 0)


def add_stabilite_secteur_hebdomadaire(
    model: cp_model.CpModel,
    x: VariableDict,
    medecins,
    jours_labels: List[str],
    postes_par_jour: Dict[int, list],
) -> TitulaireSecteurDict:
    """Contrainte dure de continuité des soins : sur une même semaine
    calendaire (lundi-vendredi), un Secteur donné (1, 2 ou 3) ne peut être
    attribué qu'à UN SEUL ET UNIQUE médecin ("titulaire" de la semaine pour ce
    secteur). Exception tolérée uniquement le(s) jour(s) où le titulaire est en
    Garde de Nuit ou en congé CE jour précis : un autre médecin peut alors
    exceptionnellement couvrir, mais le reste de la semaine revient au
    titulaire (cf. spec métier — pas de "relais" arbitraire entre médecins).

    Modélisation (par semaine, par secteur) :
    - une variable booléenne titulaire[m] par médecin candidat, avec
      sum(titulaire) == 1 si le secteur est couvert au moins un jour cette
      semaine (0 sinon : secteur totalement vacant, cas limite en pénurie) ;
    - titulaire[m] == 1 implique que m a réellement travaillé ce secteur au
      moins un jour cette semaine (pas de titulaire "fantôme") ;
    - si un médecin m1 ≠ titulaire travaille le secteur un jour donné, le
      titulaire doit être justifié absent CE jour-là : soit indisponible
      (congé, variable absente du modèle), soit affecté à GARDE_NUIT ce
      jour-là (contrainte réifiée avec OnlyEnforceIf / AddBoolOr).

    Retourne les variables titulaire construites, réutilisées par
    app.solver.objective pour bonifier la continuité PLURI-hebdomadaire
    (2-3 semaines, voire tout le mois) dans la fonction objectif."""
    groupes = _grouper_semaines(jours_labels)
    titulaires: TitulaireSecteurDict = {}

    for num_semaine, indices in enumerate(groupes):
        for secteur_code in POSTES_SECTEURS:
            jours_secteur = [
                d for d in indices if any(p.code == secteur_code for p in postes_par_jour.get(d, []))
            ]
            if not jours_secteur:
                continue
            medecins_possibles = [
                m for m in medecins if any((m.id, d, secteur_code) in x for d in jours_secteur)
            ]
            if not medecins_possibles:
                continue

            titulaire = {
                m.id: model.NewBoolVar("titulaire_s{}_{}_m{}".format(num_semaine, secteur_code, m.id))
                for m in medecins_possibles
            }

            # Le secteur n'a un titulaire (unique) que s'il est couvert au
            # moins un jour cette semaine ; sinon (semaine totalement vacante
            # sur ce secteur), aucun titulaire n'est désigné.
            vars_semaine = [
                x[(m.id, d, secteur_code)] for m in medecins_possibles for d in jours_secteur
                if (m.id, d, secteur_code) in x
            ]
            rempli = model.NewBoolVar("secteur_rempli_s{}_{}".format(num_semaine, secteur_code))
            model.AddMaxEquality(rempli, vars_semaine)
            model.Add(sum(titulaire.values()) == rempli)

            for m in medecins_possibles:
                vars_m = [
                    x[(m.id, d, secteur_code)] for d in jours_secteur if (m.id, d, secteur_code) in x
                ]
                # Un titulaire doit avoir réellement travaillé ce secteur cette
                # semaine (pas de titulaire "fantôme" qui légitimerait un
                # roulement sans jamais y être pour rien).
                model.Add(titulaire[m.id] <= sum(vars_m))

            for d in jours_secteur:
                for m2 in medecins_possibles:  # candidat titulaire potentiellement "absent justifié" ce jour
                    if (m2.id, d, secteur_code) not in x:
                        continue  # m2 indisponible (congé) ce jour-là : exception automatiquement justifiée
                    var_garde_m2 = x.get((m2.id, d, "GARDE_NUIT"))
                    for m1 in medecins_possibles:
                        if m1.id == m2.id:
                            continue
                        if (m1.id, d, secteur_code) not in x:
                            continue
                        if var_garde_m2 is not None:
                            # Si m1 (≠ titulaire) travaille le secteur ce jour et que
                            # m2 est le titulaire, m2 doit être en Garde de Nuit ce jour.
                            model.Add(var_garde_m2 == 1).OnlyEnforceIf(
                                [x[(m1.id, d, secteur_code)], titulaire[m2.id]]
                            )
                        else:
                            # m2 ne peut pas être en Garde de Nuit ce jour-là (pas de
                            # variable, poste non applicable) : aucune justification
                            # possible, la combinaison est donc interdite.
                            model.AddBoolOr(
                                [x[(m1.id, d, secteur_code)].Not(), titulaire[m2.id].Not()]
                            )

            titulaires[(num_semaine, secteur_code)] = titulaire

    return titulaires


def add_all(
    model: cp_model.CpModel,
    x: VariableDict,
    medecins,
    jours_labels: List[str],
    postes_par_jour: Dict[int, list],
    ctx: Contexte,
) -> TitulaireSecteurDict:
    add_couverture(model, x, medecins, jours_labels, postes_par_jour)
    add_unicite_par_jour(model, x, medecins, jours_labels, postes_par_jour)
    add_blocs_nuit(model, x, medecins, jours_labels, postes_par_jour)
    add_continuite_bloc_debut_mois(model, x, medecins, jours_labels, ctx)
    add_jumelage_weekend(model, x, medecins, jours_labels)
    add_max_heures_semaine(
        model, x, medecins, jours_labels, postes_par_jour, ctx.heures_semaine_partielle_precedente
    )
    add_continuite_secteurs(model, x, medecins, jours_labels, postes_par_jour, ctx)
    titulaires_secteur = add_stabilite_secteur_hebdomadaire(model, x, medecins, jours_labels, postes_par_jour)
    return titulaires_secteur
