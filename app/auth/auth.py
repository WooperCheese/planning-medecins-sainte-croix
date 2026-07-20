"""
Authentification (bcrypt) et contrôle d'accès basé sur les rôles (RBAC).

Trois rôles portés par le schéma dès la V1 : admin, medecin, rh. Seul admin a
une interface fonctionnelle en V1 ; les décorateurs/fonctions ci-dessous sont
déjà écrits pour les trois afin que les portails V2 n'aient qu'à les réutiliser.
"""

from __future__ import annotations

import functools
from typing import Callable, Iterable, Optional

import bcrypt

from app.db.models import User
from app.db.session import get_session


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def authenticate(username: str, password: str) -> Optional[User]:
    """Vérifie les identifiants. Retourne le User (détaché de la session) si OK, sinon None."""
    with get_session() as session:
        user = session.query(User).filter_by(username=username, actif=True).first()
        if user is None:
            return None
        if not verify_password(password, user.password_hash):
            return None
        session.expunge(user)
        return user


class AccessDenied(Exception):
    pass


def require_role(allowed_roles: Iterable[str]) -> Callable:
    """Décorateur : lève AccessDenied si l'utilisateur courant n'a pas un des rôles autorisés.

    La fonction décorée doit recevoir l'utilisateur courant (objet User) en
    premier argument, ou via un paramètre nommé `current_user`.
    """
    allowed = set(allowed_roles)

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            current_user = kwargs.get("current_user")
            if current_user is None and args:
                current_user = args[0]
            if current_user is None or getattr(current_user, "role", None) not in allowed:
                raise AccessDenied(
                    f"Rôle requis parmi {sorted(allowed)}, "
                    f"utilisateur a le rôle '{getattr(current_user, 'role', None)}'"
                )
            return func(*args, **kwargs)

        return wrapper

    return decorator
