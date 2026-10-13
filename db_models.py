"""
Tablas de TennisMind.
Principios: seudonimización (se usa un código por jugador, no el nombre),
minimización (solo el año de nacimiento) y supresión en cascada.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Integer,
                        String, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


def ahora() -> datetime:
    return datetime.now(timezone.utc)


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    rol: Mapped[str] = mapped_column(String(20), default="entrenador")  # admin | entrenador
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)

    tenistas: Mapped[list["Tenista"]] = relationship(
        back_populates="entrenador", cascade="all, delete-orphan", passive_deletes=True)


class Tenista(Base):
    __tablename__ = "tenistas"
    __table_args__ = (UniqueConstraint("entrenador_id", "codigo", name="uq_tenista_codigo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    entrenador_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"), index=True)
    codigo: Mapped[str] = mapped_column(String(20))        # seudónimo, p. ej. "T01"
    anio_nacimiento: Mapped[int] = mapped_column(Integer)  # solo el año (minimización)
    nivel: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)

    entrenador: Mapped["Usuario"] = relationship(back_populates="tenistas")
    consentimientos: Mapped[list["Consentimiento"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True)
    evaluaciones: Mapped[list["EvaluacionPsicologica"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True)
    partidos: Mapped[list["Partido"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True)


class Consentimiento(Base):
    __tablename__ = "consentimientos"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenista_id: Mapped[int] = mapped_column(
        ForeignKey("tenistas.id", ondelete="CASCADE"), index=True)
    version_texto: Mapped[str] = mapped_column(String(40))
    otorgado_por: Mapped[str] = mapped_column(String(30))  # jugador | representante_legal
    otorgado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)
    revocado_en: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class EvaluacionPsicologica(Base):
    __tablename__ = "evaluaciones_psicologicas"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenista_id: Mapped[int] = mapped_column(
        ForeignKey("tenistas.id", ondelete="CASCADE"), index=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)
    puntajes: Mapped[dict] = mapped_column(JSON)
    estado: Mapped[str] = mapped_column(String(20))
    confianza: Mapped[float] = mapped_column(Float)
    probabilidades: Mapped[dict] = mapped_column(JSON)
    recomendacion: Mapped[str] = mapped_column(String(300))
    alerta: Mapped[bool] = mapped_column(Boolean)
    modelo_version: Mapped[str] = mapped_column(String(20))


class Partido(Base):
    __tablename__ = "partidos"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenista_id: Mapped[int] = mapped_column(
        ForeignKey("tenistas.id", ondelete="CASCADE"), index=True)
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)
    rival_codigo: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    torneo: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    superficie: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    mediciones: Mapped[list["MedicionSet"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True)


class MedicionSet(Base):
    __tablename__ = "mediciones_set"

    id: Mapped[int] = mapped_column(primary_key=True)
    partido_id: Mapped[int] = mapped_column(
        ForeignKey("partidos.id", ondelete="CASCADE"), index=True)
    set_numero: Mapped[int] = mapped_column(Integer)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)
    entradas: Mapped[dict] = mapped_column(JSON)
    prob_p1: Mapped[float] = mapped_column(Float)
    nivel_confiabilidad: Mapped[str] = mapped_column(String(10))
    diagnostico: Mapped[str] = mapped_column(String(80))
    modelo_version: Mapped[str] = mapped_column(String(20))


class Auditoria(Base):
    """Quién hizo qué y cuándo. No guarda contenido de las evaluaciones."""
    __tablename__ = "auditoria"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True)
    accion: Mapped[str] = mapped_column(String(60))
    entidad: Mapped[str] = mapped_column(String(40))
    entidad_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)
