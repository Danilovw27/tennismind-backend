"""
TennisMind - Backend API (FastAPI)
Proyecto Integrador III - UFPSO 2026
Cumplimiento: RF-03, RF-04, RF-05, RF-06 y RNF-01 (< 2 segundos)
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import joblib
import numpy as np

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

# Cargar los modelos serializados generados en el Paso 1
try:
    modelo_psi = joblib.load("modelo_estado_psicologico.joblib")
    modelo_set = joblib.load("modelo_prediccion_set.joblib")
    print(" Modelos cargados correctamente en memoria.")
except Exception as e:
    print(f" Advertencia al cargar modelos: {e}")

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
    puntos_totales_disputados: int = Field(1, ge=1)

# ==============================================================================
# ENDPOINTS
# ==============================================================================
@app.get("/")
def health_check():
    return {"status": "online", "sistema": "TennisMind API v1.0", "latencia_esperada": "<50ms"}

@app.post("/api/evaluacion/clasificar")
def clasificar_estado_psicologico(data: EvaluacionPsicologicaInput):
    # Cálculo automático de variables consolidadas (RF-03)
    var_ansiedad_total = (data.score_ansiedad_cog + data.score_ansiedad_som + (6.0 - data.score_autoconfianza)) / 3.0
    var_momentum_neto = data.score_momentum_pos - data.score_momentum_neg
    var_fortaleza_total = (data.score_resiliencia + data.score_ctrl_emocional + data.score_perseverancia) / 3.0
    var_concentracion_total = (data.score_foco_atencional + data.score_rutinas_conc) / 2.0

    # Vector de entrada idéntico al entrenado
    vector_entrada = np.array([[
        data.score_ansiedad_cog, data.score_ansiedad_som, data.score_autoconfianza,
        data.score_momentum_pos, data.score_momentum_neg, data.score_resiliencia,
        data.score_ctrl_emocional, data.score_foco_atencional, data.score_perseverancia,
        data.score_rutinas_conc, var_ansiedad_total, var_momentum_neto,
        var_fortaleza_total, var_concentracion_total
    ]])

    # Inferencia del modelo de IA (RF-04)
    estado_predicho = modelo_psi.predict(vector_entrada)[0]
    probabilidades = modelo_psi.predict_proba(vector_entrada)[0]
    clases = list(modelo_psi.classes_)
    confianza = round(float(np.max(probabilidades)) * 100, 2)

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
        "metricas_consolidadas": {
            "ansiedad_total": round(var_ansiedad_total, 2),
            "momentum_neto": round(var_momentum_neto, 2),
            "fortaleza_total": round(var_fortaleza_total, 2),
            "concentracion_total": round(var_concentracion_total, 2)
        }
    }

@app.post("/api/partido/probabilidad-set")
def estimar_probabilidad_set(data: TelemetriaSetInput):
    # Ingeniería de características
    ace_diff = data.p1_aces - data.p2_aces
    df_diff = data.p2_dobles_faltas - data.p1_dobles_faltas
    ue_diff = data.p2_errores_noforzados - data.p1_errores_noforzados
    bp_won_diff = data.p1_break_points_ganados - data.p2_break_points_ganados
    bp_ratio_p1 = data.p1_break_points_ganados / (data.p1_break_points_totales + 1e-5)
    bp_ratio_p2 = data.p2_break_points_ganados / (data.p2_break_points_totales + 1e-5)

    vector_set = np.array([[
        ace_diff, df_diff, ue_diff, bp_won_diff, bp_ratio_p1, bp_ratio_p2, data.puntos_totales_disputados
    ]])

    prob_victoria_p1 = float(modelo_set.predict_proba(vector_set)[0][1])

    return {
        "probabilidad_ganar_set_p1": round(prob_victoria_p1 * 100, 2),
        "probabilidad_ganar_set_p2": round((1.0 - prob_victoria_p1) * 100, 2),
        "diagnostico_momentum": "Favorable a Jugador 1" if prob_victoria_p1 >= 0.55 else ("Favorable a Jugador 2" if prob_victoria_p1 <= 0.45 else "Set equilibrado")
    }