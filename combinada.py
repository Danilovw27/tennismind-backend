"""
RF-06: lectura combinada de los modelos A (estado psicológico) y B (probabilidad del set).
Son reglas escritas a mano, como las recomendaciones del Modelo A: no hay un tercer modelo
ni se guarda nada. Los textos son un borrador pendiente de validación por la asesora.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

from inferencia import TelemetriaSetInput, estimar_set

ESTADOS = ("Óptimo", "Estable", "En riesgo", "Crítico")
FRAGILES = ("En riesgo", "Crítico")
MOMENTUM_NEGATIVO = -1.0  # mismo umbral que la regla "Estable" de evaluar_psicologia

# (lectura del set, ¿estado frágil?) -> (lectura, recomendación, prioridad)
REGLAS = {
    ("favorable_j1", False): (
        "El set va a favor y el estado mental acompaña.",
        "Mantener el plan táctico y las rutinas actuales; evitar cambios innecesarios.",
        "Baja"),
    ("favorable_j1", True): (
        "El marcador favorece al jugador, pero su estado mental es frágil: hay riesgo de que se cierre el set.",
        "Proteger la ventaja: reforzar la rutina pre-saque y el enfoque punto a punto; "
        "en el próximo descanso, una técnica de respiración breve.",
        "Media"),
    ("equilibrado", False): (
        "Set parejo con buen estado mental.",
        "Apoyarse en el foco y las rutinas; buscar ajustes tácticos pequeños en el saque y los puntos de quiebre.",
        "Baja"),
    ("equilibrado", True): (
        "Set parejo con estado mental frágil: los puntos decisivos pueden inclinarse por lo emocional.",
        "Intervención breve en el próximo descanso: regulación (respiración en caja 4-4-4-4) "
        "y un objetivo simple para el siguiente juego.",
        "Media"),
    ("favorable_j2", False): (
        "El set va en contra, pero el estado mental es sólido.",
        "Priorizar el ajuste táctico (patrones, saque, nivel de riesgo asumido) sobre una intervención psicológica.",
        "Media"),
    ("favorable_j2", True): (
        "El set va en contra y el estado mental es frágil: la desventaja puede agravarse.",
        "Prioridad máxima en el próximo cambio de lado: reinicio mental (respiración y frase clave), "
        "un solo objetivo por punto y después el ajuste táctico.",
        "Alta"),
}


class LecturaCombinadaIn(BaseModel):
    estado_psicologico: Literal["Óptimo", "Estable", "En riesgo", "Crítico"]
    momentum_neto: Optional[float] = Field(None, ge=-4.0, le=4.0)  # Var_Momentum_Neto de la evaluación
    telemetria: TelemetriaSetInput


def _lectura_set(diagnostico: str, nivel: str) -> Optional[str]:
    if nivel == "Baja":
        return None
    if diagnostico.startswith("Favorable a Jugador 1"):
        return "favorable_j1"
    if diagnostico.startswith("Favorable a Jugador 2"):
        return "favorable_j2"
    return "equilibrado"


def combinar(estado: str, momentum_neto: Optional[float], resultado_set: dict) -> dict:
    """Combina el estado del Modelo A con el resultado de estimar_set()."""
    fragil = estado in FRAGILES
    notas = []
    clave = _lectura_set(resultado_set["diagnostico_momentum"], resultado_set["nivel_confiabilidad"])

    if clave is None:
        lectura = "Todavía no hay una lectura confiable del set (menos de 10 puntos jugados)."
        recomendacion = "Por ahora guiarse por el estado psicológico y repetir el cálculo cuando haya más puntos."
        prioridad = {"Crítico": "Alta", "En riesgo": "Media"}.get(estado, "Baja")
    else:
        lectura, recomendacion, prioridad = REGLAS[(clave, fragil)]

    if estado == "Crítico":
        prioridad = "Alta"
        notas.append("Estado Crítico: valorar apoyo psicológico profesional inmediato; "
                     "esta lectura no sustituye el criterio del entrenador ni del psicólogo.")
    if momentum_neto is not None and momentum_neto <= MOMENTUM_NEGATIVO:
        notas.append(f"El jugador reporta momentum negativo (neto {momentum_neto:.2f}): "
                     "cuidar la gestión del ritmo entre puntos.")

    return {
        "lectura": lectura,
        "recomendacion_combinada": recomendacion,
        "prioridad": prioridad,
        "notas": notas,
        "fuentes": {
            "estado_psicologico": estado,
            "diagnostico_set": resultado_set["diagnostico_momentum"],
            "probabilidad_ganar_set_p1": resultado_set["probabilidad_ganar_set_p1"],
            "nivel_confiabilidad": resultado_set["nivel_confiabilidad"],
        },
        "aviso": "Lectura por reglas (borrador). El Modelo A se entrenó con datos simulados; no es un diagnóstico.",
    }


def lectura_combinada(data: LecturaCombinadaIn) -> dict:
    return combinar(data.estado_psicologico, data.momentum_neto, estimar_set(data.telemetria))
