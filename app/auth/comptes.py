"""
Création, régénération, changement de mot de passe et suppression de comptes
de connexion, depuis l'interface admin (pages "Médecins & Cohortes" et
"Utilisateurs") ou en self-service (page "Mon Compte").

Séparé de app/db/seed.py (dédié au tout premier compte admin, exécuté en
ligne de commande) : ce module est appelé depuis l'UI Streamlit, où le mot de
passe généré doit être RETOURNÉ (pas juste imprimé) pour être affiché une
seule fois à l'écran.

Cf. docs/superpowers/specs/2026-07-20-portail-medecin-design.md et
docs/superpowers/specs/2026-07-20-gestion-comptes-design.md.

100% compatible Python 3.9 : Optional[...] partout, jamais de `X | None`.
"""

from __future__ import annotations

import secrets
from typing import Optional

from sqlalchemy.orm import Session

from app.auth.auth import hash_password, verify_password
from app.db.models import Role, User


class IdentifiantDejaUtilise(Exception):
    pass


class AncienMotDePasseIncorrect(Exception):
    pass


def _mot_de_passe_genere() -> str:
    return secrets.token_urlsafe(9)  # ~12 caractères lisibles, assez d'entropie pour un usage interne


def creer_compte(session: Session, username: str, role: str, medecin_id: Optional[int] = None) -> str:
    """Crée un compte de connexion pour n'importe quel rôle (admin/medecin/rh).

    Retourne le mot de passe généré en clair — à afficher une seule fois à
    l'admin, qui le transmet lui-même à la personne concernée. Jamais stocké
    en clair (seul le hash bcrypt est persisté).

    Lève IdentifiantDejaUtilise si le nom d'utilisateur est déjà pris, plutôt
    que de laisser remonter une IntegrityError brute jusqu'à l'UI.
    """
    if session.query(User).filter_by(username=username).first() is not None:
        raise IdentifiantDejaUtilise("L'identifiant '{}' est déjà utilisé.".format(username))

    mot_de_passe = _mot_de_passe_genere()
    session.add(
        User(
            username=username,
            password_hash=hash_password(mot_de_passe),
            role=role,
            medecin_id=medecin_id,
            actif=True,
        )
    )
    return mot_de_passe


def creer_compte_medecin(session: Session, medecin_id: int, username: str) -> str:
    """Crée un compte de connexion (rôle medecin) lié à un médecin existant.

    Cas particulier de creer_compte(), conservé pour ne pas changer la
    signature déjà utilisée par pages/1_Medecins_et_Cohortes.py et les tests
    existants (tests/test_portail_medecin.py).
    """
    return creer_compte(session, username, Role.MEDECIN.value, medecin_id)


def regenerer_mot_de_passe(session: Session, user_id: int) -> str:
    """Régénère le mot de passe d'un compte existant (n'importe quel rôle).

    Retourne le nouveau mot de passe en clair, à afficher une seule fois.
    """
    user = session.get(User, user_id)
    if user is None:
        raise ValueError("Utilisateur #{} introuvable.".format(user_id))

    mot_de_passe = _mot_de_passe_genere()
    user.password_hash = hash_password(mot_de_passe)
    return mot_de_passe


def changer_propre_mot_de_passe(
    session: Session, user_id: int, ancien_mot_de_passe: str, nouveau_mot_de_passe: str
) -> None:
    """Changement de mot de passe en self-service : vérifie l'ancien mot de
    passe avant de le remplacer.

    Lève AncienMotDePasseIncorrect si la vérification échoue — dans ce cas,
    rien n'est modifié (pas d'écriture avant la vérification).
    """
    user = session.get(User, user_id)
    if user is None:
        raise ValueError("Utilisateur #{} introuvable.".format(user_id))

    if not verify_password(ancien_mot_de_passe, user.password_hash):
        raise AncienMotDePasseIncorrect("L'ancien mot de passe ne correspond pas.")

    user.password_hash = hash_password(nouveau_mot_de_passe)


def supprimer_compte(session: Session, user_id: int) -> None:
    """Supprime définitivement un compte de connexion.

    Sûr côté intégrité référentielle : aucune table (Affectation,
    Indisponibilite, HeureSup) ne référence User.id — toutes pointent vers
    Medecin.id. Supprimer un compte n'affecte donc jamais la fiche médecin
    liée ni son historique.
    """
    user = session.get(User, user_id)
    if user is None:
        raise ValueError("Utilisateur #{} introuvable.".format(user_id))
    session.delete(user)
