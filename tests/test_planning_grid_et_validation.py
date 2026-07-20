import datetime

from app.solver.validation import valider_grille_manuelle
from app.ui import planning_grid as grille

UN_LUNDI = datetime.date(2026, 8, 3)


def _semaine(lundi):
    return [lundi + datetime.timedelta(days=i) for i in range(7)]


def test_colonnes_grille_couvre_les_postes_demandes():
    labels = {label for _, _, label in grille.COLONNES_GRILLE}
    for attendu in [
        "Polyclinique 8h-18h",
        "Polyclinique 10h-20h",
        "Bridge",
        "Secteur 1",
        "Secteur 2",
        "Secteur 3",
        "Garde de Nuit",
    ]:
        assert attendu in labels


def test_poste_applicable_selon_regime_jour():
    lundi = UN_LUNDI  # jour de semaine
    samedi = UN_LUNDI + datetime.timedelta(days=5)
    dimanche = UN_LUNDI + datetime.timedelta(days=6)

    assert grille.poste_applicable("POLY_MATIN", 0, lundi)
    assert not grille.poste_applicable("POLY_MATIN", 0, samedi)
    assert not grille.poste_applicable("POLY_MATIN", 0, dimanche)

    assert grille.poste_applicable("SAM_JOUR_COURT", 0, samedi)
    assert not grille.poste_applicable("SAM_JOUR_COURT", 0, lundi)

    assert grille.poste_applicable("GARDE_NUIT", 0, lundi)
    assert grille.poste_applicable("GARDE_NUIT", 0, samedi)
    assert grille.poste_applicable("GARDE_NUIT", 0, dimanche)

    # La colonne fusionnée "Journée Longue (We)" pointe vers SAM_JOUR_LONG le
    # samedi et DIM_JOUR_UNIQUE le dimanche, jamais en semaine.
    assert grille.poste_applicable(grille.JOURNEE_LONGUE_WE, 0, samedi)
    assert grille.poste_applicable(grille.JOURNEE_LONGUE_WE, 0, dimanche)
    assert not grille.poste_applicable(grille.JOURNEE_LONGUE_WE, 0, lundi)

    # Secteur 3 (comme les autres secteurs) n'existe qu'en semaine, jamais le
    # week-end.
    assert grille.poste_applicable("SECTEUR_3", 0, lundi)
    assert not grille.poste_applicable("SECTEUR_3", 0, samedi)


def test_construire_et_extraire_grille_aller_retour():
    jours = _semaine(UN_LUNDI)
    noms = {1: "Alice Test", 2: "Bob Test"}
    samedi = UN_LUNDI + datetime.timedelta(days=5)
    dimanche = UN_LUNDI + datetime.timedelta(days=6)
    affectations = [
        (UN_LUNDI, "POLY_MATIN", 1),
        (UN_LUNDI, "GARDE_NUIT", 2),
        (samedi, "SAM_JOUR_LONG", 1),
        (dimanche, "DIM_JOUR_UNIQUE", 1),
    ]

    df = grille.construire_grille(jours, affectations, noms)

    ligne_lundi = df[df[grille.COL_JOUR] == grille.ligne_label(UN_LUNDI)].iloc[0]
    assert ligne_lundi["Polyclinique 8h-18h"] == "Alice Test"
    assert ligne_lundi["Garde de Nuit"] == "Bob Test"
    # Poste non applicable ce jour-là (jour court du samedi, un lundi)
    assert ligne_lundi["Jour Court (Sam)"] == grille.NON_APPLICABLE

    ligne_samedi = df[df[grille.COL_JOUR] == grille.ligne_label(samedi)].iloc[0]
    ligne_dimanche = df[df[grille.COL_JOUR] == grille.ligne_label(dimanche)].iloc[0]
    assert ligne_samedi["Journée Longue (We)"] == "Alice Test"
    assert ligne_dimanche["Journée Longue (We)"] == "Alice Test"

    id_par_nom = {"Alice Test": 1, "Bob Test": 2}
    reconstruit = grille.extraire_affectations_editees(df, jours, id_par_nom)
    reconstruit_non_vide = [(d, p, m) for d, p, m in reconstruit if m is not None]
    assert (UN_LUNDI, "POLY_MATIN", 1) in reconstruit_non_vide
    assert (UN_LUNDI, "GARDE_NUIT", 2) in reconstruit_non_vide
    assert (samedi, "SAM_JOUR_LONG", 1) in reconstruit_non_vide
    assert (dimanche, "DIM_JOUR_UNIQUE", 1) in reconstruit_non_vide


def test_calculer_kpis():
    jours = _semaine(UN_LUNDI)
    affectations = [
        (UN_LUNDI, "POLY_MATIN", 1),
        (UN_LUNDI, "GARDE_NUIT", 2),
    ]
    kpis = grille.calculer_kpis(jours, affectations)
    assert kpis["nb_remplis"] == 2
    assert kpis["nb_gardes"] == 1
    assert 0 < kpis["taux_completion"] < 100


def test_validation_detecte_chevauchement():
    affectations = [
        (UN_LUNDI, "POLY_MATIN", 1),
        (UN_LUNDI, "GARDE_NUIT", 1),  # même médecin, même jour : interdit
    ]
    erreurs = valider_grille_manuelle(affectations, {1: "Alice Test"})
    assert len(erreurs) == 1
    assert "Alice Test" in erreurs[0]


def test_validation_detecte_depassement_50h():
    # 5 jours de Secteur 1 (10h) + 1 nuit (12h) = 62h > 50h
    affectations = [(UN_LUNDI + datetime.timedelta(days=i), "SECTEUR_1", 1) for i in range(5)]
    affectations.append((UN_LUNDI, "GARDE_NUIT", 1))
    erreurs = valider_grille_manuelle(affectations, {1: "Alice Test"})
    assert any("50h" in e or "62h" in e for e in erreurs)


def test_validation_ok_sans_erreur():
    affectations = [
        (UN_LUNDI, "POLY_MATIN", 1),
        (UN_LUNDI, "GARDE_NUIT", 2),
    ]
    erreurs = valider_grille_manuelle(affectations, {1: "Alice Test", 2: "Bob Test"})
    assert erreurs == []


def test_grille_par_medecin_affiche_poste_et_conge():
    jours = _semaine(UN_LUNDI)
    medecins_actifs = [(1, "Alice Test"), (2, "Bob Test")]
    affectations = [(UN_LUNDI, "POLY_MATIN", 1)]
    mardi = UN_LUNDI + datetime.timedelta(days=1)
    indispo = {2: {mardi}}

    df = grille.construire_grille_par_medecin(jours, affectations, medecins_actifs, indispo)

    ligne_lundi = df[df[grille.COL_JOUR] == grille.ligne_label(UN_LUNDI)].iloc[0]
    assert ligne_lundi["Alice Test"] == "Polyclinique 8h-18h"
    assert ligne_lundi["Bob Test"] == grille.VIDE

    ligne_mardi = df[df[grille.COL_JOUR] == grille.ligne_label(mardi)].iloc[0]
    assert ligne_mardi["Bob Test"] == grille.CONGE


def test_styliser_grille_par_medecin_ne_leve_pas_exception():
    jours = _semaine(UN_LUNDI)
    medecins_actifs = [(1, "Alice Test")]
    affectations = [(UN_LUNDI, "GARDE_NUIT", 1)]
    df = grille.construire_grille_par_medecin(jours, affectations, medecins_actifs, {})
    html = grille.styliser_grille_par_medecin(df).to_html()
    assert "Alice Test" in html


def test_styliser_grille_par_poste_a_des_bordures_et_du_zebre():
    jours = _semaine(UN_LUNDI)
    df = grille.construire_grille(jours, [], {})
    html = grille.styliser_grille(df).to_html()
    assert grille.BORDURE.split(" ")[0] in html  # ex: "1px" présent quelque part dans le CSS généré
    assert grille.ZEBRA_FONCE in html
