# ============================================================
# MOTOR DE REGLAS LÓGICAS
# ============================================================
#
# Reglas base:    A = P ∧ S ∧ ¬Q          acceso estándar
#                 E = P ∧ (R ∨ Q)         inspección especial
# Reglas nuevas:  T = P ∧ S ∧ R ∧ V ∧ H   retención por horario
#                 D = ¬P ∨ ¬S ∨ (R ∧ ¬V)  acceso denegado
#
# Justificación de las reglas nuevas:
# - D: las reglas base no dicen qué hacer sin autorización o con la
#   certificación vencida, y dejan pasar materiales peligrosos sin la
#   certificación específica. Sin documentos vigentes no se entra.
# - T: los materiales peligrosos no deben circular en horario
#   restringido; el camión está en regla, pero espera.
#
# Si se cumplen varias reglas, gana la más restrictiva (D > T > E > A).

from itertools import combinations, product

PREMISAS = {
    "P": "autorización previa",
    "Q": "peso excedido",
    "R": "materiales peligrosos",
    "S": "certificación del conductor vigente",
    "V": "certificación de materiales peligrosos vigente",
    "H": "horario restringido",
}

# (clave, nombre, fórmula, función, semáforo), de menos a más restrictiva
REGLAS = [
    ("A", "Acceso estándar", "P ∧ S ∧ ¬Q",
     lambda v: v["P"] and v["S"] and not v["Q"], "verde"),
    ("E", "Inspección especial", "P ∧ (R ∨ Q)",
     lambda v: v["P"] and (v["R"] or v["Q"]), "amarillo"),
    ("T", "Retención por horario restringido", "P ∧ S ∧ R ∧ V ∧ H",
     lambda v: v["P"] and v["S"] and v["R"] and v["V"] and v["H"], "amarillo"),
    ("D", "Acceso denegado", "¬P ∨ ¬S ∨ (R ∧ ¬V)",
     lambda v: not v["P"] or not v["S"] or (v["R"] and not v["V"]), "rojo"),
]
REGLAS_BASE = REGLAS[:2]


def evaluar_camion(P, Q, R, S):
    """Función original: evalúa solo las dos reglas base."""
    return {
        "autorizacion": P, "peso_excedido": Q,
        "carga_peligrosa": R, "certificacion": S,
        "acceso_estandar": P and S and not Q,
        "inspeccion_especial": P and (R or Q),
    }


def si_no(valor):
    return "Sí" if valor else "No"


def evaluar(premisas, reglas=REGLAS):
    """Evalúa las reglas y explica paso a paso la decisión.

    Devuelve un diccionario listo para guardarse en la colección accesos.
    """
    v = {p: bool(premisas.get(p, False)) for p in PREMISAS}
    pasos = ["Premisas: " + "; ".join(
        f"{p} ({PREMISAS[p]}) = {si_no(v[p])}" for p in PREMISAS)]
    resultados = {}
    for clave, _, formula, funcion, _ in reglas:
        resultados[clave] = funcion(v)
        causas = ", ".join(f"{PREMISAS[p]} ({p}) = {si_no(v[p])}"
                           for p in PREMISAS if p in formula)
        valor = "Verdadero" if resultados[clave] else "Falso"
        pasos.append(f"{clave} = {formula} → {valor}, porque {causas}.")

    activas = [r for r in reglas if resultados[r[0]]]
    if activas:
        clave, decision, _, _, semaforo = activas[-1]
        if len(activas) > 1:
            juntas = ", ".join(r[0] for r in activas)
            pasos.append(f"Se cumplen a la vez {juntas}; prevalece {clave} "
                         "por ser la más restrictiva.")
    else:
        decision, semaforo = "Revisión manual (ninguna regla aplica)", "rojo"
    pasos.append(f"Decisión final: {decision}.")
    return {**v, **resultados, "decision": decision, "semaforo": semaforo,
            "explicacion": pasos}


def premisas_de_camion(camion, Q, R, momento, inicio=22, fin=6):
    """Calcula las premisas con los datos del camión y la hora de llegada."""
    vigente = camion["certificacion_vigente_hasta"] >= momento
    hora = momento.hour
    restringido = (inicio <= hora < fin) if inicio < fin else (hora >= inicio or hora < fin)
    return {"P": camion["autorizacion"], "Q": Q, "R": R, "S": vigente,
            "V": vigente and camion["certificacion_peligrosos"],
            "H": restringido and inicio != fin}


def analizar(reglas=REGLAS):
    """Reto opcional: detecta contradicciones, redundancias y huecos."""
    casos = [dict(zip(PREMISAS, bits))
             for bits in product([False, True], repeat=len(PREMISAS))]
    verdad = {r[0]: [r[3](c) for c in casos] for r in reglas}
    semaforo = {r[0]: r[4] for r in reglas}
    lineas = []
    for a, b in combinations(verdad, 2):
        juntas = sum(x and y for x, y in zip(verdad[a], verdad[b]))
        if juntas:
            opuestas = {semaforo[a], semaforo[b]} == {"verde", "rojo"}
            tipo = "CONTRADICCIÓN" if opuestas else "Solapamiento"
            lineas.append(f"{tipo}: {a} y {b} se cumplen a la vez en "
                          f"{juntas} de {len(casos)} casos.")
        if verdad[a] == verdad[b]:
            lineas.append(f"Redundancia: {a} y {b} son equivalentes.")
        elif all(y for x, y in zip(verdad[a], verdad[b]) if x):
            lineas.append(f"Redundancia parcial: si se cumple {a} se cumple {b}.")
        elif all(x for x, y in zip(verdad[a], verdad[b]) if y):
            lineas.append(f"Redundancia parcial: si se cumple {b} se cumple {a}.")
    huecos = sum(not any(fila) for fila in zip(*verdad.values()))
    lineas.append(f"Huecos: en {huecos} de {len(casos)} casos ninguna regla "
                  "se cumple." if huecos else "Cobertura completa: siempre "
                  "se cumple al menos una regla.")
    return lineas


if __name__ == "__main__":
    for titulo, reglas in (("REGLAS BASE", REGLAS_BASE), ("TODAS", REGLAS)):
        print(f"\n--- ANÁLISIS: {titulo} ---")
        print("\n".join(analizar(reglas)))
    print("\n--- EJEMPLO: materiales peligrosos sin certificación ---")
    print("\n".join(evaluar({"P": True, "R": True, "S": True})["explicacion"]))
