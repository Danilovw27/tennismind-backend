"""Registro, inicio de sesión y administración de usuarios."""

import os
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from db_models import Auditoria, Usuario
from seguridad import (HASH_FALSO, crear_token, exigir_admin, hashear,
                       usuario_actual, verificar)

router = APIRouter(prefix="/api", tags=["Autenticación"])


class RegistroIn(BaseModel):
    email: str = Field(..., min_length=5, max_length=254,
                       pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(..., min_length=10, max_length=128)
    codigo_invitacion: str


@router.post("/auth/registro", status_code=201)
def registro(datos: RegistroIn, db: Session = Depends(get_db)):
    esperado = os.environ.get("CODIGO_INVITACION", "")
    if not esperado:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "El registro está deshabilitado")
    if not secrets.compare_digest(datos.codigo_invitacion, esperado):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Código de invitación inválido")

    email = datos.email.strip().lower()
    if db.scalar(select(Usuario).where(Usuario.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ese correo ya está registrado")

    admin_email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    usuario = Usuario(email=email, password_hash=hashear(datos.password),
                      rol="admin" if admin_email and email == admin_email else "entrenador")
    db.add(usuario)
    db.flush()
    db.add(Auditoria(usuario_id=usuario.id, accion="registro", entidad="usuario",
                     entidad_id=usuario.id))
    db.commit()
    return {"id": usuario.id, "email": usuario.email, "rol": usuario.rol}


@router.post("/auth/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    usuario = db.scalar(select(Usuario).where(Usuario.email == form.username.strip().lower()))
    # Se verifica siempre un hash, exista o no el usuario, para no revelar qué correos existen
    valido = verificar(form.password, usuario.password_hash if usuario else HASH_FALSO)
    if not (usuario and valido and usuario.activo):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Correo o contraseña incorrectos",
                            headers={"WWW-Authenticate": "Bearer"})
    db.add(Auditoria(usuario_id=usuario.id, accion="login", entidad="usuario",
                     entidad_id=usuario.id))
    db.commit()
    return {"access_token": crear_token(usuario), "token_type": "bearer"}


@router.get("/auth/yo")
def yo(usuario: Usuario = Depends(usuario_actual)):
    return {"id": usuario.id, "email": usuario.email, "rol": usuario.rol}


# ----------------------------- Administración -----------------------------
@router.get("/admin/usuarios")
def listar_usuarios(_: Usuario = Depends(exigir_admin), db: Session = Depends(get_db)):
    filas = db.scalars(select(Usuario).order_by(Usuario.id)).all()
    return [{"id": u.id, "email": u.email, "rol": u.rol, "activo": u.activo} for u in filas]


@router.post("/admin/usuarios/{usuario_id}/desactivar")
def desactivar_usuario(usuario_id: int, admin: Usuario = Depends(exigir_admin),
                       db: Session = Depends(get_db)):
    objetivo = db.get(Usuario, usuario_id)
    if objetivo is None:
        raise HTTPException(404, "Usuario no encontrado")
    if objetivo.id == admin.id:
        raise HTTPException(400, "No puedes desactivar tu propia cuenta")
    objetivo.activo = False
    db.add(Auditoria(usuario_id=admin.id, accion="desactivar_usuario", entidad="usuario",
                     entidad_id=objetivo.id))
    db.commit()
    return {"id": objetivo.id, "activo": False}


@router.get("/admin/auditoria")
def ver_auditoria(limite: int = 100, _: Usuario = Depends(exigir_admin),
                  db: Session = Depends(get_db)):
    filas = db.scalars(select(Auditoria).order_by(Auditoria.id.desc())
                       .limit(min(max(limite, 1), 500))).all()
    return [{"id": a.id, "usuario_id": a.usuario_id, "accion": a.accion, "entidad": a.entidad,
             "entidad_id": a.entidad_id, "fecha": a.creado_en} for a in filas]
