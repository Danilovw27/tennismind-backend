"""
Instrumento de 30 ítems (RF-01): carga items.json, calcula los 10 puntajes
(promedio simple de sus ítems) y los pasa al Modelo A mediante evaluar_psicologia().
items.json es la única fuente de qué ítem pertenece a qué puntaje.
"""

import json
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, Field, StrictInt

from inferencia import PuntajesPsicologicos, evaluar_psicologia

# Nombre en items.json -> nombre del campo en PuntajesPsicologicos
PUNTAJES = {
    "Score_AnsiedadCog": "score_ansiedad_cog",
    "Score_AnsiedadSom": "score_ansiedad_som",
    "Score_Autoconfianza": "score_autoconfianza",
    "Score_MomentumPos": "score_momentum_pos",
    "Score_MomentumNeg": "score_momentum_neg",
    "Score_Resiliencia": "score_resiliencia",
    "Score_CtrlEmocional": "score_ctrl_emocional",
    "Score_FocoAtencional": "score_foco_atencional",
    "Score_Perseverancia": "score_perseverancia",
    "Score_RutinasConc": "score_rutinas_conc",
}

with open(Path(__file__).with_name("items.json"), encoding="utf-8") as f:
    INSTRUMENTO = json.load(f)
ITEMS = sorted(INSTRUMENTO["items"], key=lambda i: i["numero"])
ESC_MIN = INSTRUMENTO["escala"]["min"]
ESC_MAX = INSTRUMENTO["escala"]["max"]
N_ITEMS = len(ITEMS)


def _verificar_instrumento():
    """Cada ítem existe una sola vez y pertenece a un solo puntaje conocido."""
    if [i["numero"] for i in ITEMS] != list(range(1, N_ITEMS + 1)):
        raise RuntimeError("items.json: los ítems deben estar numerados 1..N sin repetir")
    desconocidos = {i["puntaje"] for i in ITEMS} - set(PUNTAJES)
    if desconocidos:
        raise RuntimeError(f"items.json: puntajes desconocidos {sorted(desconocidos)}")
    vacios = set(PUNTAJES) - {i["puntaje"] for i in ITEMS}
    if vacios:
        raise RuntimeError(f"items.json: puntajes sin ítems {sorted(vacios)}")


_verificar_instrumento()


class RespuestasItems(BaseModel):
    """30 respuestas enteras de 1 a 5, en el orden de los ítems (la posición 0 es el ítem 1)."""
    respuestas: list[Annotated[StrictInt, Field(ge=ESC_MIN, le=ESC_MAX)]] = Field(
        ..., min_length=N_ITEMS, max_length=N_ITEMS)


class ClasificarItemsInput(RespuestasItems):
    id_tenista: str = "T01"


def calcular_puntajes(respuestas: list[int]) -> dict:
    """Promedio simple de los ítems de cada puntaje (un ítem inverso se invierte antes)."""
    if len(respuestas) != N_ITEMS:
        raise ValueError(f"Se esperaban {N_ITEMS} respuestas")
    grupos = {campo: [] for campo in PUNTAJES.values()}
    for item, r in zip(ITEMS, respuestas):
        valor = (ESC_MIN + ESC_MAX - r) if item.get("inverso") else r
        grupos[PUNTAJES[item["puntaje"]]].append(valor)
    return {campo: sum(v) / len(v) for campo, v in grupos.items()}


def evaluar_items(respuestas: list[int], id_tenista: str):
    """Devuelve (puntajes, resultado del Modelo A) a partir de las 30 respuestas."""
    puntajes = calcular_puntajes(respuestas)
    return puntajes, evaluar_psicologia(PuntajesPsicologicos(**puntajes), id_tenista=id_tenista)
