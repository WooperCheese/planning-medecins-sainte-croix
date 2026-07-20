"""
Construction des grilles affichées sur la page Planning :

- construire_grille / styliser_grille : vue globale par poste (jours en
  lignes, postes en colonnes) — c'est la grille "source de vérité" utilisée
  aussi pour l'édition manuelle (st.data_editor).
- construire_grille_par_medecin / styliser_grille_par_medecin : vue miroir,
  un médecin par colonne, pour lire d'un coup d'œil le planning d'une
  personne (lecture seule).

Toute la logique de construction/couleurs/applicabilité vit ici plutôt que
dans les scripts Streamlit, pour rester testable indépendamment de l'UI et
cohérent avec l'architecture modulaire du projet (cf. app/config.py pour les
horaires, rien n'est codé en dur ici non plus).

Note de conception (grille par poste) : le cahier des charges d'origine liste
7 colonnes (Polyclinique 8h-18h, Polyclinique 10h-20h, Bridge, Secteur
1/2/3, Garde de Nuit). Deux colonnes supplémentaires ont été ajoutées ("Jour Court (Sam)" et
"Journée Longue (We)") pour ne pas faire disparaître de la grille les postes
du week-end (Samedi 9h-17h et le tandem Samedi/Dimanche 8h-20h lié par la
règle de jumelage) : les masquer aurait fait perdre en visibilité de vraies
affectations. La colonne "Journée Longue (We)" affiche SAM_JOUR_LONG le
samedi et DIM_JOUR_UNIQUE le dimanche : comme ces deux postes sont désormais
toujours attribués au même médecin (règle de jumelage), les regrouper dans
une seule colonne reflète fidèlement la règle métier.

Lisibilité : toutes les couleurs de cellule utilisent un texte foncé
(#0F172A, bleu nuit) sauf sur les fonds très sombres (Garde de Nuit) où le
texte passe en blanc pour rester contrasté. Bordures nettes sur chaque
cellule + alternance zèbre sur les cellules vides, pour éviter tout effet
"blanc sur blanc". st.data_editor ne supporte pas ce style (limitation
Streamlit connue), d'où la vue colorée séparée en lecture seule.

100% compatible Python 3.9 : Optional[...] partout, jamais de `X | None`.
"""

from __future__ import annotations

import datetime
from typing import Dict, List, Optional, Set, Tuple, Union

import pandas as pd

from app import config
from app.solver.calendar_ch import est_ferie, jour_semaine_fr

JOURS_LABELS_COURTS = ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"]

# Code spécial (n'existe pas dans app.config) pour la colonne fusionnée Samedi/Dimanche.
JOURNEE_LONGUE_WE = "__JOURNEE_LONGUE_WE__"


def _poste_code_journee_longue(jour_label: str) -> Optional[str]:
    if jour_label == "samedi":
        return "SAM_JOUR_LONG"
    if jour_label == "dimanche":
        return "DIM_JOUR_UNIQUE"
    return None


# Structure fixe des colonnes de la grille "par poste" : (code_colonne, slot_index, libellé affiché).
# code_colonne est soit un vrai poste_code de app.config, soit JOURNEE_LONGUE_WE
# (résolu dynamiquement selon le jour via _resoudre_poste_code).
COLONNES_GRILLE: List[Tuple[str, int, str]] = [
    ("POLY_MATIN", 0, "Polyclinique 8h-18h"),
    ("POLY_JOURNEE", 0, "Polyclinique 10h-20h"),
    ("APRES_MIDI", 0, "Bridge"),
    ("SECTEUR_1", 0, "Secteur 1"),
    ("SECTEUR_2", 0, "Secteur 2"),
    ("SECTEUR_3", 0, "Secteur 3"),
    ("SAM_JOUR_COURT", 0, "Jour Court (Sam)"),
    (JOURNEE_LONGUE_WE, 0, "Journée Longue (We)"),
    ("GARDE_NUIT", 0, "Garde de Nuit"),
]


def _construire_poste_labels() -> Dict[str, str]:
    labels: Dict[str, str] = {}
    for liste in (config.POSTES_SEMAINE, config.POSTES_SAMEDI, config.POSTES_DIMANCHE):
        for p in liste:
            labels.setdefault(p.code, p.label)
    return labels


# Libellé humain pour chaque poste_code réel (utilisé par la vue par médecin).
POSTE_LABELS: Dict[str, str] = _construire_poste_labels()
_LABEL_VERS_CODE: Dict[str, str] = {v: k for k, v in POSTE_LABELS.items()}

# ---------------------------------------------------------------------------
# Palette : texte toujours foncé (#0F172A) sauf sur fond très sombre (nuit),
# où le texte passe en blanc pour rester lisible. Bordures nettes + zèbre.
# ---------------------------------------------------------------------------

TEXTE_FONCE = "#0F172A"
BORDURE = "1px solid #94a3b8"
ZEBRA_CLAIR = "#ffffff"
ZEBRA_FONCE = "#F1F5F9"

COULEURS_POSTE: Dict[str, Tuple[str, str]] = {
    "POLY_MATIN": ("#bbf0c9", TEXTE_FONCE),  # vert clair — Polyclinique 8h-18h
    "POLY_JOURNEE": ("#fde68a", TEXTE_FONCE),  # jaune/orange clair — Polyclinique 10h-20h
    "APRES_MIDI": ("#d97706", TEXTE_FONCE),  # orange foncé — Bridge
    "SECTEUR_1": ("#bfdcfb", TEXTE_FONCE),  # bleu clair — Secteurs
    "SECTEUR_2": ("#bfdcfb", TEXTE_FONCE),
    "SECTEUR_3": ("#bfdcfb", TEXTE_FONCE),
    "SAM_JOUR_COURT": ("#bfdcfb", TEXTE_FONCE),
    "SAM_JOUR_LONG": ("#bfdcfb", TEXTE_FONCE),
    "DIM_JOUR_UNIQUE": ("#bfdcfb", TEXTE_FONCE),
    JOURNEE_LONGUE_WE: ("#bfdcfb", TEXTE_FONCE),
    "GARDE_NUIT": ("#7f1d1d", "#ffffff"),  # rouge foncé, texte blanc — Garde de Nuit
}

COULEUR_NON_APPLICABLE = ("#e2e8f0", TEXTE_FONCE)  # poste qui n'existe pas ce jour (régime différent)
COULEUR_CONGE = ("#ede9fe", TEXTE_FONCE)  # violet doux, distinct des familles de postes

# ---------------------------------------------------------------------------
# Légende affichée sur la page Planning : construite à partir des mêmes
# constantes de couleur que la grille, pour ne jamais désynchroniser légende
# et grille réelle.
# ---------------------------------------------------------------------------

LEGENDE_ENTREES: List[Tuple[str, str, str]] = [
    ("POLY_MATIN", "Polyclinique 8h-18h", "8h - 18h"),
    ("POLY_JOURNEE", "Polyclinique 10h-20h", "10h - 20h"),
    ("APRES_MIDI", "Bridge", "13h - 22h"),
    ("GARDE_NUIT", "Garde de Nuit", "20h - 8h"),
    ("SECTEUR_1", "Secteurs (1/2/3, + week-ends)", "horaires classiques"),
]


def construire_legende_html() -> str:
    """Bandeau de légende (badges colorés) pour la page Planning, généré à
    partir de COULEURS_POSTE : toujours synchronisé avec les vraies couleurs
    de la grille."""
    badges = []
    for poste_code, label, horaire in LEGENDE_ENTREES:
        bg, fg = COULEURS_POSTE[poste_code]
        badges.append(
            "<span style='display:inline-block; background-color:{bg}; color:{fg}; "
            "border:1px solid #94a3b8; border-radius:6px; padding:5px 12px; "
            "margin:4px 8px 4px 0; font-weight:600; font-size:0.9rem;'>"
            "{label} <span style='font-weight:400;'>({horaire})</span></span>".format(
                bg=bg, fg=fg, label=label, horaire=horaire
            )
        )
    return "<div>{}</div>".format("".join(badges))

VIDE = ""  # cellule non affectée (poste applicable, personne assigné)
NON_APPLICABLE = "—"  # poste non applicable ce jour (ex : Polyclinique 8h-18h un dimanche)
CONGE = "CONGÉ"

COL_JOUR = "Jour"

_TABLE_STYLES = [
    {"selector": "table", "props": [("border-collapse", "collapse")]},
    {
        "selector": "th",
        "props": [
            ("border", BORDURE),
            ("background-color", "#dbeafe"),
            ("color", TEXTE_FONCE),
            ("font-weight", "700"),
            ("padding", "4px 8px"),
        ],
    },
    {"selector": "td", "props": [("padding", "4px 8px")]},
]


def ligne_label(jour: datetime.date) -> str:
    suffixe = " (férié)" if est_ferie(jour) else ""
    return "{:02d} {}{}".format(jour.day, JOURS_LABELS_COURTS[jour.weekday()], suffixe)


def _resoudre_poste_code(colonne_code: str, jour_label: str) -> Optional[str]:
    if colonne_code == JOURNEE_LONGUE_WE:
        return _poste_code_journee_longue(jour_label)
    return colonne_code


def poste_applicable(colonne_code: str, slot_index: int, jour: datetime.date) -> bool:
    """Une colonne/slot est applicable un jour donné si le régime du jour
    (semaine, samedi, dimanche, ou férié traité en régime week-end) prévoit ce
    poste avec un effectif suffisant pour ce slot."""
    label = jour_semaine_fr(jour)
    poste_code_reel = _resoudre_poste_code(colonne_code, label)
    if poste_code_reel is None:
        return False
    for p in config.get_postes_du_jour(label, est_ferie(jour)):
        if p.code == poste_code_reel:
            return slot_index < p.effectif
    return False


# ---------------------------------------------------------------------------
# Vue globale par poste (jours en lignes, postes en colonnes)
# ---------------------------------------------------------------------------


def construire_grille(
    jours: List[datetime.date],
    affectations: List[Tuple[datetime.date, str, int]],
    noms_par_medecin_id: Dict[int, str],
) -> pd.DataFrame:
    """Construit le DataFrame pivot : une ligne par jour du mois, une colonne
    par poste (cf. COLONNES_GRILLE), la valeur étant le nom du médecin affecté
    (ou VIDE / NON_APPLICABLE)."""
    par_date_poste: Dict[Tuple[datetime.date, str], List[int]] = {}
    for date, poste_code, medecin_id in affectations:
        par_date_poste.setdefault((date, poste_code), []).append(medecin_id)

    lignes = []
    for jour in jours:
        label_jour = jour_semaine_fr(jour)
        ligne = {COL_JOUR: ligne_label(jour)}
        for colonne_code, slot_index, colonne_label in COLONNES_GRILLE:
            poste_code_reel = _resoudre_poste_code(colonne_code, label_jour)
            if poste_code_reel is None or not poste_applicable(colonne_code, slot_index, jour):
                ligne[colonne_label] = NON_APPLICABLE
                continue
            medecins_ids = par_date_poste.get((jour, poste_code_reel), [])
            medecin_id = medecins_ids[slot_index] if slot_index < len(medecins_ids) else None
            ligne[colonne_label] = noms_par_medecin_id.get(medecin_id, VIDE) if medecin_id else VIDE
        lignes.append(ligne)

    colonnes = [COL_JOUR] + [label for _, _, label in COLONNES_GRILLE]
    return pd.DataFrame(lignes, columns=colonnes)


def styliser_grille(df: pd.DataFrame):
    """Pandas Styler : bordures nettes, zèbre sur les cellules vides, texte
    toujours foncé sauf sur fond de garde de nuit (texte blanc). Lecture seule
    uniquement : st.data_editor ne supporte pas ce style sur cellules éditables."""

    def style_colonne(col: pd.Series) -> List[str]:
        if col.name == COL_JOUR:
            styles = []
            for i in range(len(col)):
                zebra = ZEBRA_CLAIR if i % 2 == 0 else ZEBRA_FONCE
                styles.append(
                    "background-color: {}; color: {}; border: {}; font-weight: 700;".format(
                        zebra, TEXTE_FONCE, BORDURE
                    )
                )
            return styles

        poste_code = next((code for code, _, label in COLONNES_GRILLE if label == col.name), None)
        styles = []
        for i, valeur in enumerate(col):
            zebra = ZEBRA_CLAIR if i % 2 == 0 else ZEBRA_FONCE
            if valeur == NON_APPLICABLE:
                bg, fg = COULEUR_NON_APPLICABLE
            elif valeur == VIDE:
                bg, fg = zebra, TEXTE_FONCE
            else:
                bg, fg = COULEURS_POSTE.get(poste_code, (zebra, TEXTE_FONCE))
            styles.append("background-color: {}; color: {}; border: {}; font-weight: 500;".format(bg, fg, BORDURE))
        return styles

    return df.style.apply(style_colonne, axis=0).set_table_styles(_TABLE_STYLES)


def extraire_affectations_editees(
    df_edite: pd.DataFrame,
    jours: List[datetime.date],
    id_par_nom: Dict[str, int],
) -> List[Tuple[datetime.date, str, Optional[int]]]:
    """Reconstruit une liste (date, poste_code, medecin_id_ou_None) à partir de
    la grille éditée par l'admin. Les cellules non applicables (poste qui
    n'existe pas ce jour-là) sont ignorées même si elles ont été modifiées par
    erreur : l'applicabilité est toujours recalculée depuis la config, jamais
    déduite du contenu de la cellule."""
    resultat: List[Tuple[datetime.date, str, Optional[int]]] = []
    for position, jour in enumerate(jours):
        ligne = df_edite.iloc[position]
        label_jour = jour_semaine_fr(jour)
        for colonne_code, slot_index, colonne_label in COLONNES_GRILLE:
            poste_code_reel = _resoudre_poste_code(colonne_code, label_jour)
            if poste_code_reel is None or not poste_applicable(colonne_code, slot_index, jour):
                continue
            valeur = ligne[colonne_label]
            medecin_id = id_par_nom.get(valeur) if valeur not in (VIDE, NON_APPLICABLE) else None
            resultat.append((jour, poste_code_reel, medecin_id))
    return resultat


def calculer_kpis(
    jours: List[datetime.date],
    affectations: List[Tuple[datetime.date, str, int]],
) -> Dict[str, Union[int, float]]:
    """Indicateurs affichés en haut de la page Planning : nombre de slots
    applicables ce mois, nombre remplis, taux de complétion, nombre total de
    gardes de nuit générées."""
    nb_applicables = 0
    for jour in jours:
        for colonne_code, slot_index, _label in COLONNES_GRILLE:
            if poste_applicable(colonne_code, slot_index, jour):
                nb_applicables += 1

    nb_remplis = len(affectations)
    nb_gardes = sum(1 for _date, poste_code, _mid in affectations if poste_code == "GARDE_NUIT")
    taux_completion = round(100.0 * nb_remplis / nb_applicables, 1) if nb_applicables else 0.0

    return {
        "nb_applicables": nb_applicables,
        "nb_remplis": nb_remplis,
        "taux_completion": taux_completion,
        "nb_gardes": nb_gardes,
    }


# ---------------------------------------------------------------------------
# Vue par médecin (jours en lignes, médecins en colonnes) — lecture seule
# ---------------------------------------------------------------------------


def construire_grille_par_medecin(
    jours: List[datetime.date],
    affectations: List[Tuple[datetime.date, str, int]],
    medecins_actifs: List[Tuple[int, str]],
    indispo_par_medecin: Dict[int, Set[datetime.date]],
) -> pd.DataFrame:
    """Une ligne par jour du mois, une colonne par médecin actif ; la cellule
    contient le nom du poste occupé ce jour-là, "CONGÉ" si une indisponibilité
    couvre ce jour, ou une cellule vide sinon."""
    par_date_medecin: Dict[Tuple[datetime.date, int], str] = {}
    for date, poste_code, medecin_id in affectations:
        par_date_medecin[(date, medecin_id)] = poste_code

    lignes = []
    for jour in jours:
        ligne = {COL_JOUR: ligne_label(jour)}
        for medecin_id, nom in medecins_actifs:
            poste_code = par_date_medecin.get((jour, medecin_id))
            if poste_code is not None:
                ligne[nom] = POSTE_LABELS.get(poste_code, poste_code)
            elif jour in indispo_par_medecin.get(medecin_id, set()):
                ligne[nom] = CONGE
            else:
                ligne[nom] = VIDE
        lignes.append(ligne)

    colonnes = [COL_JOUR] + [nom for _id, nom in medecins_actifs]
    return pd.DataFrame(lignes, columns=colonnes)


def styliser_grille_par_medecin(df: pd.DataFrame):
    """Même charte visuelle que styliser_grille (bordures, zèbre, texte
    foncé garanti), mais la couleur d'une cellule dépend ici du POSTE qu'elle
    contient (retrouvé depuis le libellé) plutôt que de sa colonne, puisque
    les colonnes sont des médecins et non des postes."""

    def style_colonne(col: pd.Series) -> List[str]:
        if col.name == COL_JOUR:
            styles = []
            for i in range(len(col)):
                zebra = ZEBRA_CLAIR if i % 2 == 0 else ZEBRA_FONCE
                styles.append(
                    "background-color: {}; color: {}; border: {}; font-weight: 700;".format(
                        zebra, TEXTE_FONCE, BORDURE
                    )
                )
            return styles

        styles = []
        for i, valeur in enumerate(col):
            zebra = ZEBRA_CLAIR if i % 2 == 0 else ZEBRA_FONCE
            if valeur == CONGE:
                bg, fg = COULEUR_CONGE
            elif valeur == VIDE:
                bg, fg = zebra, TEXTE_FONCE
            else:
                poste_code = _LABEL_VERS_CODE.get(valeur)
                bg, fg = COULEURS_POSTE.get(poste_code, (zebra, TEXTE_FONCE))
            styles.append("background-color: {}; color: {}; border: {}; font-weight: 500;".format(bg, fg, BORDURE))
        return styles

    return df.style.apply(style_colonne, axis=0).set_table_styles(_TABLE_STYLES)
