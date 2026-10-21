"""
RF-02: observaciones del entrenador (Instrumento 2). Mismas reglas que el resto de datos del jugador:
consentimiento vigente para guardar, cada entrenador ve solo lo suyo y el administrador no lee nada.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from db_models import ObservacionEntrenador, Partido, Usuario
from instrumento_observacion import ObservacionIn, calcular_puntajes, hay_riesgo
from rutas_tenistas import _auditar, _exigir_consentimiento, _partido_o_404, _tenista_o_404
from seguridad import usuario_actual

router = APIRouter(prefix="/api", tags=["Observación del entrenador (requieren sesión)"])


def _serializar(o: ObservacionEntrenador, p: Partido = None) -> dict:
    fila = {"id": o.id, "partido_id": o.partido_id, "seccion": o.seccion, "set_numero": o.set_numero,
            "fecha": o.creado_en, "respuestas": o.respuestas, "notas": o.notas, "puntajes": o.puntajes,
            "alertas": o.alertas, "analisis": o.analisis,
            "alerta_activa": hay_riesgo(o.respuestas, o.alertas)}
    if p is not None:
        fila["partido"] = {"fecha": p.fecha, "torneo": p.torneo, "rival_codigo": p.rival_codigo}
    return fila


@router.post("/partidos/{partido_id}/observaciones", status_code=201)
def registrar_observacion(partido_id: int, datos: ObservacionIn, db: Session = Depends(get_db),
                          usuario: Usuario = Depends(usuario_actual)):
    p = _partido_o_404(db, partido_id, usuario)
    _exigir_consentimiento(db, p.tenista_id)
    previas = db.scalars(select(ObservacionEntrenador).where(
        ObservacionEntrenador.partido_id == p.id, ObservacionEntrenador.seccion == datos.seccion)).all()
    if datos.seccion in ("A", "C") and previas:
        raise HTTPException(409, f"Este partido ya tiene la sección {datos.seccion}")
    if datos.seccion == "B" and any(o.set_numero == datos.set_numero for o in previas):
        raise HTTPException(409, f"Este partido ya tiene la sección B del set {datos.set_numero}")

    analisis = dict(datos.analisis)
    if datos.resultado_set:
        analisis["resultado_set"] = datos.resultado_set
    o = ObservacionEntrenador(
        tenista_id=p.tenista_id, partido_id=p.id, seccion=datos.seccion, set_numero=datos.set_numero,
        respuestas={str(n): v for n, v in datos.respuestas.items()},
        notas={str(n): t for n, t in datos.notas.items()},
        puntajes=calcular_puntajes(datos.seccion, datos.respuestas),
        alertas=datos.alertas, analisis=analisis)
    db.add(o)
    db.flush()
    _auditar(db, usuario, "crear_observacion", "observacion", o.id)
    db.commit()
    return _serializar(o)


@router.get("/partidos/{partido_id}/observaciones")
def listar_observaciones_partido(partido_id: int, db: Session = Depends(get_db),
                                 usuario: Usuario = Depends(usuario_actual)):
    p = _partido_o_404(db, partido_id, usuario)
    filas = db.scalars(select(ObservacionEntrenador).where(ObservacionEntrenador.partido_id == p.id)
                       .order_by(ObservacionEntrenador.id)).all()
    return [_serializar(o) for o in filas]


@router.get("/tenistas/{tenista_id}/observaciones")
def listar_observaciones_tenista(tenista_id: int, limite: int = 200, db: Session = Depends(get_db),
                                 usuario: Usuario = Depends(usuario_actual)):
    t = _tenista_o_404(db, tenista_id, usuario)
    filas = db.execute(select(ObservacionEntrenador, Partido)
                       .join(Partido, Partido.id == ObservacionEntrenador.partido_id)
                       .where(ObservacionEntrenador.tenista_id == t.id)
                       .order_by(ObservacionEntrenador.id.desc())
                       .limit(min(max(limite, 1), 500))).all()
    _auditar(db, usuario, "consultar_observaciones", "tenista", t.id)
    db.commit()
    return [_serializar(o, p) for o, p in filas]
