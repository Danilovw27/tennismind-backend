"""
TennisMind - Backend API (FastAPI)
Proyecto Integrador III - UFPSO 2026
Cumplimiento: RF-03, RF-04, RF-05, RF-06 y RNF-01 (< 2 segundos)
"""

import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

import db_models  # noqa: F401  (registra las tablas en Base)
from database import Base, engine
from db_models import Usuario
from inferencia import (META_PSI, META_SET, EvaluacionPsicologicaInput,
                        TelemetriaSetInput, estimar_set, evaluar_psicologia)
from rutas_auth import router as auth_router
from rutas_tenistas import router as tenistas_router
from seguridad import usuario_actual


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)  # crea las tablas que falten (no modifica las existentes)
    yield


app = FastAPI(
    title="TennisMind API",
    description="API REST para monitoreo psicológico y predicción táctica en tenis",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS: CORS_ORIGINS = dominios separados por coma (p. ej. la URL de Vercel).
# Sin definir, acepta cualquier origen (útil mientras se desarrolla).
ORIGENES = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGENES,
    allow_credentials=False,  # la sesión viaja en el encabezado Authorization, no en cookies
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(tenistas_router)


@app.get("/")
def health_check():
    return {
        "status": "online",
        "sistema": "TennisMind API",
        "modelos": {"psicologico": META_PSI.get("version"), "set": META_SET.get("version")},
    }


# Endpoints de cálculo sin guardar datos: requieren sesión iniciada.
@app.post("/api/evaluacion/clasificar")
def clasificar_estado_psicologico(data: EvaluacionPsicologicaInput,
                                  _: Usuario = Depends(usuario_actual)):
    return evaluar_psicologia(data, id_tenista=data.id_tenista)


@app.post("/api/partido/probabilidad-set")
def estimar_probabilidad_set(data: TelemetriaSetInput, _: Usuario = Depends(usuario_actual)):
    return estimar_set(data)
