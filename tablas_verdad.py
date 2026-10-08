# ============================================================
# TABLA DE VERDAD DEL SISTEMA LOGISMART
# ============================================================

from itertools import product

from logica import REGLAS


def tabla_verdad(reglas=REGLAS, premisas="PQRSVH"):
    """Devuelve (encabezados, filas) con todas las combinaciones."""
    encabezados = list(premisas) + [r[0] for r in reglas]
    filas = []
    for bits in product([False, True], repeat=len(premisas)):
        valores = {**dict.fromkeys("PQRSVH", False), **dict(zip(premisas, bits))}
        filas.append([int(b) for b in bits] + [int(r[3](valores)) for r in reglas])
    return encabezados, filas


def generar_tabla_verdad():
    """Imprime la tabla de verdad de cada regla con sus propias premisas."""
    for regla in REGLAS:
        premisas = "".join(p for p in "PQRSVH" if p in regla[2])
        encabezados, filas = tabla_verdad([regla], premisas)
        print(f"\n{regla[0]} = {regla[2]}   ({regla[1]})")
        print(" ".join(encabezados))
        for fila in filas:
            print(" ".join(str(c) for c in fila))


if __name__ == "__main__":
    generar_tabla_verdad()
