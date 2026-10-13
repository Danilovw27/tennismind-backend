"""
TennisMind - Backend API (FastAPI)
Proyecto Integrador III - UFPSO 2026
Cumplimiento: RF-03, RF-04, RF-05, RF-06 y RNF-01 (< 2 segundos)
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator
import json
import joblib
import numpy as np
import pandas as pd
import sklearn

app = FastAPI(
    title="TennisMind API",
    description="API REST para monitoreo psicológico y predicción táctica en tenis",
    version="1.0.0"
)

# Configuración CORS para permitir conexión desde React
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cargar los modelos serializados (si falta algún archivo, el servidor no arranca)
def cargar_modelo(nombre):
    modelo = joblib.load(f"{nombre}.joblib")
    with open(f"{nombre}.json", encoding="utf-8") as f:
        meta = json.load(f)
    if meta.get("sklearn") != sklearn.__version__:
        print(f" Aviso: {nombre} entrenado con scikit-learn {meta.get('sklearn')}, "
              f"servidor usa {sklearn.__version__}")
    return modelo, meta

modelo_psi, META_PSI = cargar_modelo("modelo_estado_psicologico_v2")
modelo_set, META_SET = cargar_modelo("modelo_prediccion_set_v2")
FEATURES_PSI = META_PSI["features"]  # fuente única del orden de variables
FEATURES_SET = META_SET["features"]
print(" Modelos cargados correctamente en memoria.")

# ==============================================================================
# ESQUEMAS DE DATOS (PYDANTIC)
# ==============================================================================
class EvaluacionPsicologicaInput(BaseModel):
    id_tenista: str = "T01"
    score_ansiedad_cog: float = Field(..., ge=1.0, le=5.0)
    score_ansiedad_som: float = Field(..., ge=1.0, le=5.0)
    score_autoconfianza: float = Field(..., ge=1.0, le=5.0)
    score_momentum_pos: float = Field(..., ge=1.0, le=5.0)
    score_momentum_neg: float = Field(..., ge=1.0, le=5.0)
    score_resiliencia: float = Field(..., ge=1.0, le=5.0)
    score_ctrl_emocional: float = Field(..., ge=1.0, le=5.0)
    score_foco_atencional: float = Field(..., ge=1.0, le=5.0)
    score_perseverancia: float = Field(..., ge=1.0, le=5.0)
    score_rutinas_conc: float = Field(..., ge=1.0, le=5.0)

class TelemetriaSetInput(BaseModel):
    """Estado del set en curso, visto desde el Jugador 1 (el tenista monitoreado)."""
    p1_juegos: int = Field(0, ge=0, le=7)
    p2_juegos: int = Field(0, ge=0, le=7)
    saque_p1: bool = True  # True si el Jugador 1 saca el próximo punto
    p1_aces: int = Field(0, ge=0)
    p2_aces: int = Field(0, ge=0)
    p1_dobles_faltas: int = Field(0, ge=0)
    p2_dobles_faltas: int = Field(0, ge=0)
    p1_errores_noforzados: int = Field(0, ge=0)
    p2_errores_noforzados: int = Field(0, ge=0)
    p1_break_points_ganados: int = Field(0, ge=0)
    p2_break_points_ganados: int = Field(0, ge=0)
    p1_break_points_totales: int = Field(0, ge=0)
    p2_break_points_totales: int = Field(0, ge=0)
    puntos_totales_disputados: int = Field(0, ge=0)  # puntos jugados hasta ahora en el set

    @model_validator(mode="after")
    def validar_coherencia(self):
        if self.p1_break_points_ganados > self.p1_break_points_totales:
            raise ValueError("Break points ganados (J1) no puede superar los totales")
        if self.p2_break_points_ganados > self.p2_break_points_totales:
            raise ValueError("Break points ganados (Rival) no puede superar los totales")
        if self.puntos_totales_disputados < self.p1_juegos + self.p2_juegos:
            raise ValueError("Los puntos jugados no pueden ser menos que los juegos disputados")
        return self

# ==============================================================================
# ENDPOINTS
# ==============================================================================
@app.get("/")
def health_check():
    return {"status": "online", "sistema": "TennisMind API v1.0", "latencia_esperada": "<50ms"}

@app.post("/api/evaluacion/clasificar")
def clasificar_estado_psicologico(data: EvaluacionPsicologicaInput):
    # Variables consolidadas (RF-03): fórmulas idénticas a las del dataset de entrenamiento
    var_ansiedad_total = (5 * data.score_ansiedad_cog + 3 * data.score_ansiedad_som) / 8.0
    var_momentum_neto = data.score_momentum_pos - data.score_momentum_neg
    var_fortaleza_total = (data.score_resiliencia + data.score_ctrl_emocional + data.score_perseverancia) / 3.0
    var_concentracion_total = (2 * data.score_foco_atencional + 4 * data.score_rutinas_conc) / 6.0

    caracteristicas = {
        "Var_Ansiedad_Total": var_ansiedad_total,
        "Var_Momentum_Neto": var_momentum_neto,
        "Var_Fortaleza_Total": var_fortaleza_total,
        "Var_Concentracion_Total": var_concentracion_total,
    }
    vector_entrada = pd.DataFrame([caracteristicas], columns=FEATURES_PSI)

    # Inferencia del modelo de IA (RF-04)
    probabilidades = modelo_psi.predict_proba(vector_entrada)[0]
    clases = list(modelo_psi.classes_)
    idx = int(np.argmax(probabilidades))
    estado_predicho = clases[idx]
    confianza = round(float(probabilidades[idx]) * 100, 2)
    prob_por_clase = {
        c: round(float(probabilidades[clases.index(c)]) * 100, 1)
        for c in ("Óptimo", "Estable", "En riesgo", "Crítico") if c in clases
    }

    # Generación de recomendación de intervención (RF-05) basada en literatura
    if estado_predicho == 'Óptimo':
        recomendacion = "Mantener rutinas actuales y foco competitivo."
        alerta = False
    elif estado_predicho == 'Crítico':
        recomendacion = "Intervención psicológica inmediata: protocolo de contención y respiración diafragmática."
        alerta = True
    elif estado_predicho == 'En riesgo':
        alerta = True
        if var_concentracion_total < 3.0:
            recomendacion = "Protocolo de concentración urgente: redefinir rutinas pre-saque de 4 segundos."
        elif var_fortaleza_total < 3.0:
            recomendacion = "Intervención en fortaleza mental: autodiálogo positivo y enfoque punto a punto."
        else:
            recomendacion = "Sesión de regulación emocional: aplicar técnica de respiración en caja (Box Breathing 4-4-4-4)."
    else:  # Estable
        alerta = False
        if data.score_ansiedad_cog > 3.5:
            recomendacion = "Trabajar control de ansiedad cognitiva: desviar atención del marcador."
        elif var_momentum_neto < -1.0:
            recomendacion = "Reforzar gestión del momentum negativo: ralentizar el ritmo entre saques."
        else:
            recomendacion = "Reforzar autoconfianza y validar aciertos tácticos."

    return {
        "id_tenista": data.id_tenista,
        "estado_psicologico": estado_predicho,
        "confianza_prediccion_pct": confianza,
        "alerta_activa": alerta,
        "recomendacion_entrenador": recomendacion,
        "probabilidades_por_clase_pct": prob_por_clase,
        "modelo_version": META_PSI.get("version", "v2"),
        "metricas_consolidadas": {
            "ansiedad_total": round(var_ansiedad_total, 2),
            "momentum_neto": round(var_momentum_neto, 2),
            "fortaleza_total": round(var_fortaleza_total, 2),
            "concentracion_total": round(var_concentracion_total, 2)
        }
    }

@app.post("/api/partido/probabilidad-set")
def estimar_probabilidad_set(data: TelemetriaSetInput):
    # Ingeniería de características: idéntica a la del notebook de entrenamiento (v2)
    caracteristicas = {
        "games_diff": data.p1_juegos - data.p2_juegos,
        "ace_diff": data.p1_aces - data.p2_aces,
        "df_diff": data.p2_dobles_faltas - data.p1_dobles_faltas,
        "ue_diff": data.p2_errores_noforzados - data.p1_errores_noforzados,
        "bp_won_diff": data.p1_break_points_ganados - data.p2_break_points_ganados,
        "bp_ratio_diff": (
            data.p1_break_points_ganados / (data.p1_break_points_totales + 1)
            - data.p2_break_points_ganados / (data.p2_break_points_totales + 1)
        ),
        "saque_p1": int(data.saque_p1),
        "games_total": data.p1_juegos + data.p2_juegos,
        "pts_jugados": data.puntos_totales_disputados,
    }
    vector_set = pd.DataFrame([caracteristicas], columns=FEATURES_SET)

    prob_victoria_p1 = float(modelo_set.predict_proba(vector_set)[0][1])

    # Fiabilidad según el avance del set (AUC en partidos de prueba: 0-9 pts ~0.60;
    # 10-19 ~0.76; 20+ ~0.81-0.84)
    pts = data.puntos_totales_disputados
    if pts < 10:
        nivel = "Baja"
        diagnostico = "Muestra insuficiente (menos de 10 puntos jugados)"
    else:
        nivel = "Media" if pts < 20 else "Alta"
        if prob_victoria_p1 >= 0.55:
            diagnostico = "Favorable a Jugador 1"
        elif prob_victoria_p1 <= 0.45:
            diagnostico = "Favorable a Jugador 2"
        else:
            diagnostico = "Set equilibrado"

    return {
        "probabilidad_ganar_set_p1": round(prob_victoria_p1 * 100, 2),
        "probabilidad_ganar_set_p2": round((1.0 - prob_victoria_p1) * 100, 2),
        "diagnostico_momentum": diagnostico,
        "nivel_confiabilidad": nivel,
        "modelo_version": META_SET.get("version", "v2"),
    }
