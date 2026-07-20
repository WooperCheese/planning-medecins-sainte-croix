"""
Modèle de données SQLAlchemy.

Le schéma porte déjà les 3 rôles (admin / medecin / rh) dès la V1, même si seule
l'interface admin est implémentée pour l'instant : ça évite une migration de
schéma quand les portails médecin et RH seront ajoutés en V2.
"""

from __future__ import annotations

import datetime
import enum
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Role(str, enum.Enum):
    ADMIN = "admin"
    MEDECIN = "medecin"
    RH = "rh"


class TypeIndisponibilite(str, enum.Enum):
    CONGE = "conge"
    MALADIE = "maladie"
    FORMATION = "formation"
    AUTRE = "autre"


class StatutAffectation(str, enum.Enum):
    GENERE = "genere"
    MODIFIE_MANUELLEMENT = "modifie_manuellement"


class Cohorte(Base):
    """Une période de roulement des médecins assistants (cycle Mai-Mai ou Nov-Nov)."""

    __tablename__ = "cohortes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    date_debut: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    date_fin: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    archivee: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    medecins: Mapped[list["Medecin"]] = relationship(back_populates="cohorte")

    def __repr__(self) -> str:
        return f"<Cohorte {self.label}>"


class Medecin(Base):
    """Un médecin assistant actif ou passé du service."""

    __tablename__ = "medecins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nom: Mapped[str] = mapped_column(String(100), nullable=False)
    prenom: Mapped[str] = mapped_column(String(100), nullable=False)
    cohorte_id: Mapped[int] = mapped_column(ForeignKey("cohortes.id"), nullable=False)
    actif: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    date_arrivee: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    date_depart: Mapped[Optional[datetime.date]] = mapped_column(Date, nullable=True)
    # Présent pour extension future (temps partiel). Fixé à 100 pour tous en V1 :
    # le solver et les calculs de quota ne gèrent pas encore le prorata.
    taux_activite: Mapped[int] = mapped_column(Integer, default=100, nullable=False)

    cohorte: Mapped["Cohorte"] = relationship(back_populates="medecins")
    indisponibilites: Mapped[list["Indisponibilite"]] = relationship(back_populates="medecin")
    affectations: Mapped[list["Affectation"]] = relationship(back_populates="medecin")

    def nom_complet(self) -> str:
        return f"{self.prenom} {self.nom}"

    def __repr__(self) -> str:
        return f"<Medecin {self.nom_complet()}>"


class User(Base):
    """Compte de connexion. Rôle admin/medecin/rh, lié optionnellement à un Medecin."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    medecin_id: Mapped[Optional[int]] = mapped_column(ForeignKey("medecins.id"), nullable=True)
    actif: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    medecin: Mapped[Optional["Medecin"]] = relationship()

    def __repr__(self) -> str:
        return f"<User {self.username} ({self.role})>"


class Indisponibilite(Base):
    """Congé, maladie, formation ou autre indisponibilité déclarée par l'admin."""

    __tablename__ = "indisponibilites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    medecin_id: Mapped[int] = mapped_column(ForeignKey("medecins.id"), nullable=False)
    date_debut: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    date_fin: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    commentaire: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    medecin: Mapped["Medecin"] = relationship(back_populates="indisponibilites")


class Affectation(Base):
    """Une affectation médecin <-> poste pour un jour donné."""

    __tablename__ = "affectations"
    __table_args__ = (
        UniqueConstraint("date", "poste_code", "medecin_id", name="uq_affectation_slot"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    poste_code: Mapped[str] = mapped_column(String(50), nullable=False)
    medecin_id: Mapped[int] = mapped_column(ForeignKey("medecins.id"), nullable=False)
    statut: Mapped[str] = mapped_column(String(30), default=StatutAffectation.GENERE.value)
    degrade: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    medecin: Mapped["Medecin"] = relationship(back_populates="affectations")


class HeureSup(Base):
    """Heures supplémentaires déclarées par un médecin (portail médecin, V2)."""

    __tablename__ = "heures_sup"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    medecin_id: Mapped[int] = mapped_column(ForeignKey("medecins.id"), nullable=False)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    nb_heures: Mapped[float] = mapped_column(nullable=False)
    motif: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, nullable=False
    )

    medecin: Mapped["Medecin"] = relationship()


class GenerationLog(Base):
    """Trace de chaque génération de planning, y compris les postes sacrifiés."""

    __tablename__ = "generation_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    semaine_debut: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    date_generation: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, nullable=False
    )
    admin_username: Mapped[str] = mapped_column(String(100), nullable=False)
    postes_sacrifies_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    faisable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
