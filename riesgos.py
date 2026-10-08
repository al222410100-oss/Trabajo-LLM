# ============================================================
# EVALUACIÓN ÉTICA Y MATRIZ DE RIESGOS
# ============================================================
#
# Cada riesgo se evalúa dos veces en escala 1 a 5:
#   puntaje inicial  = probabilidad × impacto            (antes de mitigar)
#   puntaje residual = probabilidad_residual × impacto_residual (después)

import json
import os


class EvaluadorRiesgosIA:
    """Clase original: registra riesgos en memoria y los exporta a JSON."""

    def __init__(self):
        self.riesgos = []

    def registrar_riesgo(self, modulo, riesgo, categoria, impacto, probabilidad, mitigacion):
        self.riesgos.append({"modulo": modulo, "riesgo": riesgo, "categoria": categoria,
                             "impacto": impacto, "probabilidad": probabilidad,
                             "mitigacion": mitigacion})

    def mostrar_riesgos(self):
        for numero, riesgo in enumerate(self.riesgos, 1):
            print(f"\nRiesgo #{numero}")
            for campo, valor in riesgo.items():
                print(f"  {campo}: {valor}")

    def exportar_reporte(self, archivo):
        os.makedirs(os.path.dirname(archivo) or ".", exist_ok=True)
        with open(archivo, "w", encoding="utf-8") as f:
            json.dump({"total_riesgos": len(self.riesgos), "riesgos": self.riesgos},
                      f, indent=4, ensure_ascii=False)


# Riesgos propios del sistema:
# (módulo, categoría, descripción, prob., impacto, mitigación, prob. res., impacto res.)
RIESGOS_INICIALES = [
    ("Asistente LLM", "alucinacion",
     "El LLM puede inventar motivos o datos de un acceso que no existen.", 4, 5,
     "RAG: responde solo con registros de MongoDB, cita la fuente y sin datos "
     "contesta «no tengo información» sin llamar al modelo.", 2, 4),
    ("Clasificador de correos", "sesgo",
     "Los correos con ortografía informal pueden recibir menor prioridad.", 4, 4,
     "Normalizar el texto, fusionar con reglas quedándose con la prioridad más "
     "alta y evaluar con correos informales.", 2, 3),
    ("Base de datos", "privacidad",
     "Se almacena el nombre del conductor, que es un dato personal.", 3, 5,
     "LLM local, el nombre del conductor no se envía al modelo y solo se "
     "guardan los datos necesarios.", 2, 4),
    ("Operación", "automatizacion",
     "El operador acepta la decisión del sistema sin revisarla.", 4, 4,
     "Explicación paso a paso, marca «requiere revisión humana» y edición "
     "manual del resultado.", 3, 3),
]


def puntajes(riesgo):
    """Devuelve (puntaje inicial, puntaje residual)."""
    return (riesgo["probabilidad"] * riesgo["impacto"],
            riesgo["probabilidad_residual"] * riesgo["impacto_residual"])


def nivel(puntaje):
    return ("crítico" if puntaje >= 15 else "alto" if puntaje >= 10
            else "medio" if puntaje >= 5 else "bajo")


def cargar_riesgos_iniciales(bd):
    """Da de alta los riesgos propios del sistema si la colección está vacía."""
    if bd.listar("riesgos_eticos"):
        return 0
    campos = ("modulo", "categoria", "descripcion", "probabilidad", "impacto",
              "mitigacion", "probabilidad_residual", "impacto_residual")
    for valores in RIESGOS_INICIALES:
        bd.guardar("riesgos_eticos", dict(zip(campos, valores)))
    return len(RIESGOS_INICIALES)


if __name__ == "__main__":
    for datos in RIESGOS_INICIALES:
        inicial, residual = datos[3] * datos[4], datos[6] * datos[7]
        print(f"{datos[0]:<25} {inicial:>2} ({nivel(inicial)}) -> "
              f"{residual:>2} ({nivel(residual)})")
