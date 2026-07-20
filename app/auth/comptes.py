"""
Création et régénération de comptes de connexion pour un médecin, depuis
l'interface admin (page "Médecins & Cohortes").

Séparé de app/db/seed.py (dédié au tout premier compte admin, exécuté en
ligne de commande) : ce module est appelé depuis l'UI Streamlit, où le mot de
passe généré doit être RETOURNÉ (pas juste imprimé) pour être affiché une
seule fois à l'écran.

Cf. docs/superpowers/specs/2026-07-20-portail-medecin-design.md.

100% compatible Python 3.9 : Optional[...] partout, jamais de `X | None`.
"""

from __future__ import annotations

import secrets

from sqlalchemy.orm import Session

from app.auth.auth import hash_password
from app.db.models import Role, User


class IdentifiantDejaUtilise(Exception):
    pass


def _mot_de_passe_genere() -> str:
    return secrets.token_urlsafe(9)  # ~12 caractères lisibles, assez d'entropie pour un usage interne


def creer_compte_medecin(session: Session, medecin_id: int, username: str) -> str:
    """Crée un compte de connexion (rôle medecin) lié à un médecin existant.

    Retourne le mot de passe généré en clair — à afficher une seule fois à
    l'admin, qui le transmet lui-même au médecin concerné. Jamais stocké en
    clair (seul le hash bcrypt est persisté).

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
            role=Role.MEDECIN.value,
            medecin_id=medecin_id,
            actif=True,
        )
    )
    return mot_de_passe


def regenerer_mot_de_passe(session: Session, user_id: int) -> str:
    """Régénère le mot de passe d'un compte existant (medecin ou admin).

    Retourne le nouveau mot de passe en clair, à afficher une seule fois.
    """
    user = session.get(User, user_id)
    if user is None:
        raise ValueError("Utilisateur #{} introuvable.".format(user_id))

    mot_de_passe = _mot_de_passe_genere()
    user.password_hash = hash_password(mot_de_passe)
    return mot_de_passe
