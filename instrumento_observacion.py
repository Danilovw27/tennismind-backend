"""
RF-02: Instrumento 2 (guía de observación del entrenador). Carga items_observacion.json,
valida cada sección y calcula los puntajes por dimensión (promedio simple; el ítem 21 va invertido).
Los ítems 26-30 son evaluación global: se guardan, pero no entran en ningún promedio.
"""

import json
from pathlib import Path
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field, StrictInt, model_validator

from items_instrumento import PUNTAJES  # Score_* -> campo de PuntajesPsicologicos

with open(Path(__file__).with_name("items_observacion.json"), encoding="utf-8") as f:
    INSTRUMENTO = json.load(f)
ESC_MIN = INSTRUMENTO["escala"]["min"]
ESC_MAX = INSTRUMENTO["escala"]["max"]
ITEMS = {i["numero"]: i for i in INSTRUMENTO["items"]}
SECCIONES = {k: range(v["items"][0], v["items"][1] + 1) for k, v in INSTRUMENTO["secciones"].items()}
ALERTAS = {a["id"]: a["texto"] for a in INSTRUMENTO["alertas_riesgo"]}
PREGUNTAS = {q["id"]: q["pregunta"] for q in INSTRUMENTO["analisis_cualitativo"]}
ITEM_INDICADOR_RIESGO = 29  # valor alto = más riesgo (ver "nota" en items_observacion.json)
UMBRAL_RIESGO = 4


def _verificar_instrumento():
    if sorted(ITEMS) != list(range(1, 31)) or len(INSTRUMENTO["items"]) != 30:
        raise RuntimeError("items_observacion.json: los ítems deben ser 1..30, cada uno una vez")
    cubiertos = sorted(n for r in SECCIONES.values() for n in r)
    if cubiertos != list(range(1, 31)):
        raise RuntimeError("items_observacion.json: las secciones deben cubrir los 30 ítems sin solaparse")
    for n, it in ITEMS.items():
        if it["seccion"] not in SECCIONES or n not in SECCIONES[it["seccion"]]:
            raise RuntimeError(f"items_observacion.json: el ítem {n} no coincide con su sección")
        if (it["puntaje"] is None) != (it["grupo"] == "global"):
            raise RuntimeError(f"items_observacion.json: el ítem {n} mezcla puntaje y evaluación global")
        if it["puntaje"] is not None and it["puntaje"] not in PUNTAJES:
            raise RuntimeError(f"items_observacion.json: puntaje desconocido en el ítem {n}")


_verificar_instrumento()


class ObservacionIn(BaseModel):
    seccion: Literal["A", "B", "C"]
    set_numero: Optional[int] = Field(None, ge=1, le=5)  # obligatorio solo en B
    resultado_set: Optional[str] = Field(None, pattern=r"^\d{1,2}-\d{1,2}(\(\d{1,2}\))?$")  # p. ej. "6-4"
    respuestas: dict[int, Annotated[StrictInt, Field(ge=ESC_MIN, le=ESC_MAX)]]
    notas: dict[int, Annotated[str, Field(max_length=300)]] = {}
    alertas: list[str] = []
    analisis: dict[str, Annotated[str, Field(max_length=1000)]] = {}

    @model_validator(mode="after")
    def validar(self):
        if self.seccion == "B" and self.set_numero is None:
            raise ValueError("La sección B se registra por set: falta set_numero")
        if self.seccion != "B" and (self.set_numero is not None or self.resultado_set is not None):
            raise ValueError("set_numero y resultado_set solo aplican a la sección B")
        esperados = set(SECCIONES[self.seccion])
        if set(self.respuestas) != esperados:
            raise ValueError(f"La sección {self.seccion} debe traer exactamente los ítems "
                             f"{min(esperados)} a {max(esperados)}")
        if not set(self.notas) <= esperados:
            raise ValueError("Hay notas de ítems que no pertenecen a la sección")
        self.notas = {n: t.strip() for n, t in self.notas.items() if t.strip()}
        if len(set(self.alertas)) != len(self.alertas) or not set(self.alertas) <= set(ALERTAS):
            raise ValueError("Alertas de riesgo no válidas o repetidas")
        if not set(self.analisis) <= set(PREGUNTAS):
            raise ValueError("Preguntas cualitativas no válidas")
        self.analisis = {k: t.strip() for k, t in self.analisis.items() if t.strip()}
        return self


def calcular_puntajes(seccion: str, respuestas: dict) -> dict:
    """Promedio simple por dimensión con los ítems de la sección (ítem inverso: min + max - valor)."""
    grupos: dict[str, list] = {}
    for n in SECCIONES[seccion]:
        it = ITEMS[n]
        if it["puntaje"] is None:
            continue
        v = respuestas[n]
        grupos.setdefault(PUNTAJES[it["puntaje"]], []).append(ESC_MIN + ESC_MAX - v if it["inverso"] else v)
    return {campo: sum(v) / len(v) for campo, v in grupos.items()}


def hay_riesgo(respuestas: dict, alertas: list) -> bool:
    """Alerta si el entrenador marcó alguna de R1-R6 o el ítem 29 (señales de riesgo) es alto."""
    valores = {int(k): v for k, v in respuestas.items()}
    return bool(alertas) or valores.get(ITEM_INDICADOR_RIESGO, 0) >= UMBRAL_RIESGO
