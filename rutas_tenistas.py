"""
Jugadores, consentimiento, evaluaciones psicológicas, partidos y mediciones.
Regla central: sin consentimiento vigente no se guarda ningún dato del jugador.
Cada entrenador solo accede a sus propios jugadores (el administrador tampoco
lee datos psicológicos: gestiona cuentas, no evaluaciones).
"""

from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from db_models import (Auditoria, Consentimiento, EvaluacionPsicologica, MedicionSet,
                       Partido, Tenista, Usuario)
from inferencia import PuntajesPsicologicos, TelemetriaSetInput, estimar_set, evaluar_psicologia
from items_instrumento import RespuestasItems, evaluar_items
from seguridad import usuario_actual

router = APIRouter(prefix="/api", tags=["Datos del jugador (requieren sesión)"])


# ------------------------------- Esquemas -------------------------------
class TenistaIn(BaseModel):
    codigo: str = Field(..., pattern=r"^[A-Za-z0-9_-]{2,20}$")
    anio_nacimiento: int = Field(..., ge=1940, le=datetime.now().year)
    nivel: Optional[str] = Field(None, max_length=40)


class ConsentimientoIn(BaseModel):
    version_texto: str = Field(..., min_length=1, max_length=40)
    otorgado_por: Literal["jugador", "representante_legal"]


class PartidoIn(BaseModel):
    rival_codigo: Optional[str] = Field(None, max_length=40)
    torneo: Optional[str] = Field(None, max_length=80)
    superficie: Optional[str] = Field(None, max_length=30)


class MedicionIn(TelemetriaSetInput):
    set_numero: int = Field(1, ge=1, le=5)


# ------------------------------- Auxiliares -------------------------------
def _auditar(db: Session, usuario: Usuario, accion: str, entidad: str, entidad_id=None):
    db.add(Auditoria(usuario_id=usuario.id, accion=accion, entidad=entidad,
                     entidad_id=entidad_id))


def _tenista_o_404(db: Session, tenista_id: int, usuario: Usuario) -> Tenista:
    t = db.get(Tenista, tenista_id)
    # 404 (y no 403) para no revelar qué identificadores existen
    if t is None or t.entrenador_id != usuario.id:
        raise HTTPException(404, "Jugador no encontrado")
    return t


def _consentimiento_vigente(db: Session, tenista_id: int) -> Optional[Consentimiento]:
    return db.scalars(
        select(Consentimiento)
        .where(Consentimiento.tenista_id == tenista_id, Consentimiento.revocado_en.is_(None))
        .order_by(Consentimiento.otorgado_en.desc())).first()


def _exigir_consentimiento(db: Session, tenista_id: int):
    if _consentimiento_vigente(db, tenista_id) is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "El jugador no tiene consentimiento vigente; no se pueden guardar datos")


def _puede_ser_menor(t: Tenista) -> bool:
    # Solo se guarda el año de nacimiento: criterio conservador (hasta 18 años cumplidos en el año)
    return datetime.now(timezone.utc).year - t.anio_nacimiento <= 18


# ------------------------------- Jugadores -------------------------------
@router.post("/tenistas", status_code=201)
def crear_tenista(datos: TenistaIn, db: Session = Depends(get_db),
                  usuario: Usuario = Depends(usuario_actual)):
    existe = db.scalar(select(Tenista).where(Tenista.entrenador_id == usuario.id,
                                             Tenista.codigo == datos.codigo))
    if existe:
        raise HTTPException(409, "Ya tienes un jugador con ese código")
    t = Tenista(entrenador_id=usuario.id, **datos.model_dump())
    db.add(t)
    db.flush()
    _auditar(db, usuario, "crear_tenista", "tenista", t.id)
    db.commit()
    return {"id": t.id, "codigo": t.codigo, "anio_nacimiento": t.anio_nacimiento,
            "nivel": t.nivel, "requiere_representante_legal": _puede_ser_menor(t),
            "consentimiento_vigente": False}


@router.get("/tenistas")
def listar_tenistas(db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_actual)):
    filas = db.scalars(select(Tenista).where(Tenista.entrenador_id == usuario.id)
                       .order_by(Tenista.id)).all()
    return [{"id": t.id, "codigo": t.codigo, "anio_nacimiento": t.anio_nacimiento,
             "nivel": t.nivel, "requiere_representante_legal": _puede_ser_menor(t),
             "consentimiento_vigente": _consentimiento_vigente(db, t.id) is not None}
            for t in filas]


@router.delete("/tenistas/{tenista_id}", status_code=204)
def eliminar_tenista(tenista_id: int, db: Session = Depends(get_db),
                     usuario: Usuario = Depends(usuario_actual)):
    """Derecho de supresión: borra al jugador y, en cascada, todos sus datos."""
    t = _tenista_o_404(db, tenista_id, usuario)
    _auditar(db, usuario, "eliminar_tenista", "tenista", t.id)
    db.delete(t)
    db.commit()
    return Response(status_code=204)


# ------------------------------- Consentimiento -------------------------------
@router.post("/tenistas/{tenista_id}/consentimiento", status_code=201)
def registrar_consentimiento(tenista_id: int, datos: ConsentimientoIn,
                             db: Session = Depends(get_db),
                             usuario: Usuario = Depends(usuario_actual)):
    t = _tenista_o_404(db, tenista_id, usuario)
    if _puede_ser_menor(t) and datos.otorgado_por != "representante_legal":
        raise HTTPException(422, "Por su edad, el consentimiento debe darlo su representante legal")
    if _consentimiento_vigente(db, t.id):
        raise HTTPException(409, "Ya existe un consentimiento vigente")
    c = Consentimiento(tenista_id=t.id, **datos.model_dump())
    db.add(c)
    db.flush()
    _auditar(db, usuario, "registrar_consentimiento", "consentimiento", c.id)
    db.commit()
    return {"id": c.id, "otorgado_por": c.otorgado_por, "version_texto": c.version_texto,
            "otorgado_en": c.otorgado_en}


@router.post("/tenistas/{tenista_id}/consentimiento/revocar")
def revocar_consentimiento(tenista_id: int, db: Session = Depends(get_db),
                           usuario: Usuario = Depends(usuario_actual)):
    t = _tenista_o_404(db, tenista_id, usuario)
    c = _consentimiento_vigente(db, t.id)
    if c is None:
        raise HTTPException(404, "No hay consentimiento vigente")
    c.revocado_en = datetime.now(timezone.utc)
    _auditar(db, usuario, "revocar_consentimiento", "consentimiento", c.id)
    db.commit()
    return {"id": c.id, "revocado_en": c.revocado_en,
            "nota": "No se guardarán nuevos datos. Para suprimir los existentes, elimina al jugador."}


# ------------------------------- Evaluaciones (Modelo A) -------------------------------
def _guardar_evaluacion(db: Session, usuario: Usuario, t: Tenista, puntajes: dict, r: dict) -> dict:
    ev = EvaluacionPsicologica(
        tenista_id=t.id, puntajes=puntajes, estado=r["estado_psicologico"],
        confianza=r["confianza_prediccion_pct"], probabilidades=r["probabilidades_por_clase_pct"],
        recomendacion=r["recomendacion_entrenador"], alerta=r["alerta_activa"],
        modelo_version=r["modelo_version"])
    db.add(ev)
    db.flush()
    _auditar(db, usuario, "crear_evaluacion", "evaluacion", ev.id)
    db.commit()
    return {"id": ev.id, "fecha": ev.creado_en, **r}


@router.post("/tenistas/{tenista_id}/evaluaciones", status_code=201)
def crear_evaluacion(tenista_id: int, puntajes: PuntajesPsicologicos,
                     db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_actual)):
    t = _tenista_o_404(db, tenista_id, usuario)
    _exigir_consentimiento(db, t.id)
    r = evaluar_psicologia(puntajes, id_tenista=t.codigo)
    return _guardar_evaluacion(db, usuario, t, puntajes.model_dump(), r)


@router.post("/tenistas/{tenista_id}/evaluaciones-items", status_code=201)
def crear_evaluacion_items(tenista_id: int, datos: RespuestasItems,
                           db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_actual)):
    """RF-01: recibe las 30 respuestas. Se guardan en el JSON "puntajes" (clave "items"),
    junto a los 10 puntajes calculados; no se crean columnas ni tablas."""
    t = _tenista_o_404(db, tenista_id, usuario)
    _exigir_consentimiento(db, t.id)
    puntajes, r = evaluar_items(datos.respuestas, t.codigo)
    guardado = _guardar_evaluacion(db, usuario, t, {**puntajes, "items": datos.respuestas}, r)
    return {**guardado, "puntajes": puntajes}


@router.get("/tenistas/{tenista_id}/evaluaciones")
def listar_evaluaciones(tenista_id: int, limite: int = 100, db: Session = Depends(get_db),
                        usuario: Usuario = Depends(usuario_actual)):
    t = _tenista_o_404(db, tenista_id, usuario)
    filas = db.scalars(select(EvaluacionPsicologica)
                       .where(EvaluacionPsicologica.tenista_id == t.id)
                       .order_by(EvaluacionPsicologica.id.desc())
                       .limit(min(max(limite, 1), 500))).all()
    _auditar(db, usuario, "consultar_evaluaciones", "tenista", t.id)
    db.commit()
    return [{"id": e.id, "fecha": e.creado_en, "estado": e.estado, "confianza": e.confianza,
             "probabilidades": e.probabilidades, "alerta": e.alerta,
             "recomendacion": e.recomendacion, "puntajes": e.puntajes,
             "modelo_version": e.modelo_version} for e in filas]


# ------------------------------- Partidos y mediciones (Modelo B) -------------------------------
@router.post("/tenistas/{tenista_id}/partidos", status_code=201)
def crear_partido(tenista_id: int, datos: PartidoIn, db: Session = Depends(get_db),
                  usuario: Usuario = Depends(usuario_actual)):
    t = _tenista_o_404(db, tenista_id, usuario)
    _exigir_consentimiento(db, t.id)
    p = Partido(tenista_id=t.id, **datos.model_dump())
    db.add(p)
    db.flush()
    _auditar(db, usuario, "crear_partido", "partido", p.id)
    db.commit()
    return {"id": p.id, "fecha": p.fecha, "rival_codigo": p.rival_codigo,
            "torneo": p.torneo, "superficie": p.superficie}


def _partido_o_404(db: Session, partido_id: int, usuario: Usuario) -> Partido:
    p = db.get(Partido, partido_id)
    if p is None:
        raise HTTPException(404, "Partido no encontrado")
    _tenista_o_404(db, p.tenista_id, usuario)  # verifica que sea de este entrenador
    return p


@router.post("/partidos/{partido_id}/mediciones", status_code=201)
def registrar_medicion(partido_id: int, datos: MedicionIn, db: Session = Depends(get_db),
                       usuario: Usuario = Depends(usuario_actual)):
    p = _partido_o_404(db, partido_id, usuario)
    _exigir_consentimiento(db, p.tenista_id)
    entradas = datos.model_dump(exclude={"set_numero"})
    r = estimar_set(TelemetriaSetInput(**entradas))
    m = MedicionSet(partido_id=p.id, set_numero=datos.set_numero, entradas=entradas,
                    prob_p1=r["probabilidad_ganar_set_p1"],
                    nivel_confiabilidad=r["nivel_confiabilidad"],
                    diagnostico=r["diagnostico_momentum"], modelo_version=r["modelo_version"])
    db.add(m)
    db.flush()
    _auditar(db, usuario, "registrar_medicion", "medicion", m.id)
    db.commit()
    return {"id": m.id, "fecha": m.creado_en, "set_numero": m.set_numero, **r}


@router.get("/partidos/{partido_id}/mediciones")
def listar_mediciones(partido_id: int, db: Session = Depends(get_db),
                      usuario: Usuario = Depends(usuario_actual)):
    p = _partido_o_404(db, partido_id, usuario)
    filas = db.scalars(select(MedicionSet).where(MedicionSet.partido_id == p.id)
                       .order_by(MedicionSet.id)).all()
    return [{"id": m.id, "fecha": m.creado_en, "set_numero": m.set_numero,
             "probabilidad_ganar_set_p1": m.prob_p1,
             "nivel_confiabilidad": m.nivel_confiabilidad, "diagnostico": m.diagnostico,
             "entradas": m.entradas, "modelo_version": m.modelo_version} for m in filas]
