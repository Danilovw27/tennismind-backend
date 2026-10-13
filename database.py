"""
Conexión a la base de datos (Neon / PostgreSQL).
La cadena de conexión viene de la variable de entorno DATABASE_URL.
"""

import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker


def _normalizar_url(url: str) -> str:
    # Neon entrega "postgresql://..."; SQLAlchemy con psycopg 3 necesita "postgresql+psycopg://..."
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("Falta la variable de entorno DATABASE_URL")
DATABASE_URL = _normalizar_url(DATABASE_URL)

if DATABASE_URL.startswith("postgresql"):
    # pool_pre_ping: Neon suspende el cómputo tras unos minutos sin uso y cierra las
    #   conexiones inactivas; así el pool las comprueba y se reconecta solo.
    # prepare_threshold=None: evita sentencias preparadas, necesario con el pooler (PgBouncer).
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args={"prepare_threshold": None},
    )
else:  # SQLite, solo para pruebas locales
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _activar_claves_foraneas(conexion, _):
        conexion.execute("PRAGMA foreign_keys=ON")

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
