"""
Utilitaire ponctuel : réinitialise le mot de passe d'un utilisateur existant
(par défaut "admin"). À utiliser en ligne de commande, avec DATABASE_URL
pointé vers la base cible (Neon ou locale) :

    DATABASE_URL="postgresql://..." python -m app.db.reset_password

En attendant qu'une vraie fonction "changer le mot de passe" existe dans
l'interface (sous-projet gestion des comptes utilisateurs, pas encore fait),
ce script est le seul moyen de réinitialiser un mot de passe oublié/perdu
(getpass ne permet pas de relire une saisie passée, et le mot de passe n'est
de toute façon jamais stocké en clair, seulement son hash bcrypt).

100% compatible Python 3.9 : Optional[...] partout, jamais de `X | None`.
"""

from __future__ import annotations

import getpass
import sys

from app.auth.auth import hash_password
from app.db.models import User
from app.db.session import get_session


def reinitialiser_mot_de_passe(username: str = "admin") -> None:
    with get_session() as session:
        user = session.query(User).filter_by(username=username).first()
        if user is None:
            print("[reset_password] Aucun utilisateur '{}' trouvé.".format(username))
            sys.exit(1)

        password = getpass.getpass("Nouveau mot de passe pour '{}' : ".format(username))
        confirmation = getpass.getpass("Confirme le mot de passe : ")
        if password != confirmation:
            print("[reset_password] Les deux saisies ne correspondent pas, rien n'a été changé.")
            sys.exit(1)
        if not password:
            print("[reset_password] Mot de passe vide refusé, rien n'a été changé.")
            sys.exit(1)

        user.password_hash = hash_password(password)
        print("[reset_password] Mot de passe de '{}' mis à jour.".format(username))


if __name__ == "__main__":
    cible = sys.argv[1] if len(sys.argv) > 1 else "admin"
    reinitialiser_mot_de_passe(cible)
