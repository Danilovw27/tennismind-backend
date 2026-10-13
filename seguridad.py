"""Contraseñas (Argon2) y autenticación con JWT."""

import os
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from database import get_db
from db_models import Usuario

SECRET_KEY = os.environ.get("SECRET_KEY", "")
if len(SECRET_KEY) < 32:
    raise RuntimeError("SECRET_KEY debe existir y tener al menos 32 caracteres")
ALGORITMO = "HS256"
MINUTOS_TOKEN = int(os.environ.get("ACCESS_TOKEN_MINUTES", "480"))

_ph = PasswordHasher()
# Hash de relleno: se verifica cuando el correo no existe, para igualar tiempos de respuesta
HASH_FALSO = _ph.hash("relleno-para-igualar-tiempos")

oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hashear(password: str) -> str:
    return _ph.hash(password)


def verificar(password: str, hash_guardado: str) -> bool:
    try:
        return _ph.verify(hash_guardado, password)
    except (VerificationError, InvalidHashError):
        return False


def crear_token(usuario: Usuario) -> str:
    expira = datetime.now(timezone.utc) + timedelta(minutes=MINUTOS_TOKEN)
    return jwt.encode({"sub": str(usuario.id), "rol": usuario.rol, "exp": expira},
                      SECRET_KEY, algorithm=ALGORITMO)


def usuario_actual(token: str = Depends(oauth2), db: Session = Depends(get_db)) -> Usuario:
    error = HTTPException(status.HTTP_401_UNAUTHORIZED, "Credenciales inválidas o sesión expirada",
                          headers={"WWW-Authenticate": "Bearer"})
    try:
        datos = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITMO])
        usuario = db.get(Usuario, int(datos["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError):
        raise error
    if usuario is None or not usuario.activo:
        raise error
    return usuario


def exigir_admin(usuario: Usuario = Depends(usuario_actual)) -> Usuario:
    if usuario.rol != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo para administradores")
    return usuario
