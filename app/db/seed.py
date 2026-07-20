"""
Initialisation de la base : création des tables + compte admin par défaut
s'il n'en existe encore aucun.
"""

from __future__ import annotations

import getpass
import secrets

from app.auth.auth import hash_password
from app.db.models import Role, User
from app.db.session import get_session, init_db


def ensure_default_admin() -> None:
    """Crée un compte admin si aucun utilisateur n'existe encore.

    Le mot de passe est demandé interactivement si le script tourne dans un
    terminal, sinon un mot de passe aléatoire est généré et affiché une seule
    fois (à changer immédiatement après la première connexion).
    """
    with get_session() as session:
        if session.query(User).count() > 0:
            return

        username = "admin"
        try:
            password = getpass.getpass(f"Mot de passe pour le compte '{username}' : ")
        except Exception:
            password = ""

        if not password:
            password = secrets.token_urlsafe(12)
            print(f"[seed] Aucun mot de passe saisi. Mot de passe généré : {password}")
            print("[seed] Change-le dès la première connexion.")

        admin = User(
            username=username,
            password_hash=hash_password(password),
            role=Role.ADMIN.value,
            actif=True,
        )
        session.add(admin)


if __name__ == "__main__":
    init_db()
    ensure_default_admin()
    print("[seed] Base initialisée.")
