# ============================================================
# CLASIFICADOR DE INCIDENTES Y ASISTENTE EXPLICATIVO
# ============================================================
#
# 1. Funciones originales.
# 2. Correos etiquetados a mano (para el experimento y las demos).
# 3. Clasificador por reglas, con LLM e híbrido.
# 4. Experimento: exactitud, matriz de confusión y latencia.
# 5. Asistente explicativo (RAG sencillo sobre MongoDB).

import json
import re
import time
import unicodedata
from datetime import datetime

import ollama
from pydantic import ValidationError

from base_datos import CATEGORIAS, PRIORIDADES, Clasificacion

MODELO = "llama3.2"


# ============================================================
# 1. FUNCIONES ORIGINALES
# ============================================================

def clasificar_incidente(tipo, descripcion, nivel):
    """Procesa un incidente y devuelve exclusivamente JSON."""
    prioridad = ("CRITICA" if nivel >= 8 else "ALTA" if nivel >= 5
                 else "MEDIA" if nivel >= 3 else "BAJA")
    incidente = {"tipo": tipo, "descripcion": descripcion, "nivel": nivel,
                 "prioridad": prioridad, "fecha": datetime.now().isoformat()}
    return json.dumps({"incidente": incidente}, indent=4, ensure_ascii=False)


def enviar_correo_soporte(destinatario, asunto, mensaje):
    """Simulación del envío de correo."""
    print("\n========== CORREO DE SOPORTE ==========")
    print("Destinatario:", destinatario, "\nAsunto:", asunto, "\nMensaje:", mensaje)


# ============================================================
# 2. CORREOS ETIQUETADOS A MANO: (texto, categoría, prioridad)
# ============================================================
# Varios tienen ortografía informal para medir el sesgo del clasificador.

CORREOS = [
    ("El camión CAM-101 de Transportes Norte pasó por la báscula con 4 toneladas por encima del límite. Solicito instrucciones.", "peso", "alta"),
    ("oigan el kamion CAM-104 trae sobrepezo, la bascula marco 48 ton y el limite es 40, k hago??", "peso", "alta"),
    ("La unidad con placa XYZ-789 excede el peso máximo por eje. Queda detenida en la caseta 2 hasta redistribuir la carga.", "peso", "alta"),
    ("Consulta: ¿cuál es el peso máximo permitido para un tractocamión de cinco ejes? Es para planear envíos.", "peso", "baja"),
    ("La báscula de la caseta 3 marca valores distintos cada vez que pesa el mismo camión.", "mantenimiento", "media"),
    ("URGENTE: el camión CAM-103 presenta un derrame de ácido sulfúrico en el patio. Hay dos trabajadores con irritación en los ojos.", "materiales_peligrosos", "critica"),
    ("El CAM-105 de Químicos del Bajío llegó con carga inflamable y el conductor no trae la certificación de materiales peligrosos.", "materiales_peligrosos", "alta"),
    ("ay una fuga de gas en la pipa placas GHI-321, huele muy fuerte, ya sacamos a la gente d la caseta", "materiales_peligrosos", "critica"),
    ("Aviso: mañana a las 23:00 llega un embarque de cloro de Químicos del Bajío. Favor de confirmar si puede ingresar.", "materiales_peligrosos", "media"),
    ("Las etiquetas de material corrosivo del remolque del CAM-103 están despintadas. Solicito que se reemplacen.", "materiales_peligrosos", "media"),
    ("La certificación del conductor del camión CAM-106 venció el mes pasado. No se le permitió el ingreso.", "documentacion", "alta"),
    ("buenas, al chofer del CAM-102 se le olvidaron los papeles del seguro, dice q los manda x whats, lo dejo pasar?", "documentacion", "media"),
    ("Adjunto la póliza de seguro actualizada de las unidades de Logística Sur para que la registren.", "documentacion", "baja"),
    ("La carta porte del camión con placa ABC-123 no coincide con la carga: declara cemento y trae varilla.", "documentacion", "alta"),
    ("Recordatorio: las licencias de cuatro conductores de Transportes Norte vencen dentro de 30 días.", "documentacion", "baja"),
    ("El camión CAM-104 llegó sin autorización previa y el conductor insiste en entrar. Urge respuesta.", "acceso", "alta"),
    ("no me dejan entrar en la caseta 1, traigo cita a las 10 y el sistema dice q no estoy autorizado, placas JKL-654", "acceso", "media"),
    ("Solicito dar de alta la autorización de acceso para la unidad CAM-110 de Fletes del Centro a partir del lunes.", "acceso", "baja"),
    ("La barrera de la caseta 2 no levanta y hay una fila de doce camiones bloqueando la entrada.", "mantenimiento", "alta"),
    ("¿Cuál es el horario de atención de la caseta de ingreso los fines de semana? Gracias.", "acceso", "baja"),
    ("Accidente en el andén 4: el CAM-101 golpeó a un montacargas. El operador está herido y ya se llamó a la ambulancia.", "seguridad", "critica"),
    ("El conductor del camión con placa MNO-987 llegó con aliento alcohólico y se comporta de forma agresiva.", "seguridad", "critica"),
    ("se metieron a robar al patio anoche, le kitaron las llantas a un remolque y rompieron el candado d la reja", "seguridad", "alta"),
    ("Se observó a una persona sospechosa tomando fotografías de los camiones durante la madrugada.", "seguridad", "media"),
    ("Incendio en la cabina del CAM-105 dentro del estacionamiento. Se usaron los extintores y no hay lesionados.", "seguridad", "critica"),
    ("El camión CAM-102 reporta falla en los frenos al llegar a la caseta. Se recomienda no permitir que continúe.", "mantenimiento", "alta"),
    ("una llanta del remolque d la unidad PQR-246 esta ponchada, puede esperar en el patio mientras llega el taller?", "mantenimiento", "media"),
    ("Las luces del pasillo de inspección llevan tres días apagadas. Solicito mantenimiento.", "mantenimiento", "media"),
    ("La cámara de lectura de placas de la caseta 1 está fuera de servicio desde ayer.", "mantenimiento", "media"),
    ("Les comparto la invitación a la comida de fin de año del personal. Favor de confirmar asistencia.", "otro", "baja"),
    ("Buenas tardes, ¿me pueden enviar una cotización del servicio de almacenaje por mes? Saludos.", "otro", "baja"),
    ("gracias x la atencion de ayer, todo salio bien con la entrega", "otro", "baja"),
]


# ============================================================
# 3. CLASIFICADORES
# ============================================================

# El orden resuelve los empates: primero lo más grave.
PALABRAS = {
    "materiales_peligrosos": "peligros quimic inflamable corrosiv derrame acido cloro pipa|fuga de gas",
    "seguridad": "accidente golpeo robo robar herid lesion incendio sospechos agresiv alcohol ambulancia",
    "peso": "peso pezo bascula tonelada|por eje",
    "documentacion": "certificac licencia papeles vencio vencen poliza seguro|carta porte",
    "acceso": "acceso autorizac autorizado entrar caseta cita",
    "mantenimiento": "frenos llanta falla taller luces ponchad|fuera de servicio|no levanta",
}
URGENCIA = {
    "critica": "derrame fuga incendio herid lesionad accidente ambulancia alcohol",
    "alta": "urgente urge bloquea sobrepeso sobrepezo excede vencio robar frenos|por encima|sin autorizacion|no coincide|no trae",
    "baja": "consulta cotizacion recordatorio gracias invitacion adjunto|dar de alta|horario de atencion",
}


def normalizar(texto):
    """Minúsculas y sin acentos, para comparar con las palabras clave."""
    plano = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in plano if unicodedata.category(c) != "Mn")


def claves(cadena):
    """'a b|c d' -> ['a', 'b', 'c d'] (la barra separa frases con espacios)."""
    palabras, *frases = cadena.split("|")
    return palabras.split() + frases


def extraer_entidades(texto):
    camion = re.search(r"\bCAM[\s-]?(\d{3,6})\b", texto, re.I)
    placa = re.search(r"\b(?!CAM)([A-Z]{3})-(\d{3,4})\b", texto)
    empresa = re.search(r"(Transportes Norte|Logística Sur|Químicos del Bajío"
                        r"|Fletes del Centro)", texto)
    return {"camion_id": f"CAM-{camion.group(1)}" if camion else None,
            "placa": placa.group(0) if placa else None,
            "empresa": empresa.group(0) if empresa else None}


def clasificar_por_reglas(texto):
    """Clasificador de respaldo: solo palabras clave."""
    plano = normalizar(texto)
    puntos = {c: sum(p in plano for p in claves(lista)) for c, lista in PALABRAS.items()}
    categoria = max(puntos, key=puntos.get) if any(puntos.values()) else "otro"
    prioridad = next((nivel for nivel, lista in URGENCIA.items()
                      if any(p in plano for p in claves(lista))), "media")
    return {"categoria": categoria, "prioridad": prioridad,
            "entidades": extraer_entidades(texto), "resumen": texto.strip()[:150]}


PROMPT_CLASIFICACION = """
Eres el clasificador de correos de incidentes de LogiSmart, un centro de
control de acceso de camiones de carga. Lee el correo y devuelve SOLO un
objeto JSON con este esquema exacto:

{"categoria": "acceso" | "peso" | "materiales_peligrosos" | "documentacion"
              | "seguridad" | "mantenimiento" | "otro",
 "prioridad": "baja" | "media" | "alta" | "critica",
 "entidades": {"camion_id": texto o null, "placa": texto o null, "empresa": texto o null},
 "resumen": una frase en español de máximo 200 caracteres}

Categorías:
- acceso: autorizaciones, citas, ingreso a las instalaciones.
- peso: sobrepeso, básculas, límites de carga.
- materiales_peligrosos: químicos, inflamables, derrames, fugas.
- documentacion: licencias, certificaciones, pólizas, carta porte.
- seguridad: accidentes, heridos, robos, incendios, conductas de riesgo.
- mantenimiento: fallas mecánicas o de equipos e instalaciones.
- otro: lo que no encaje en las anteriores.

Prioridades:
- critica: hay o puede haber daño a personas (heridos, fuego, derrame, fuga).
- alta: incumplimiento que impide operar o exige decidir hoy.
- media: problema que puede esperar unas horas.
- baja: consultas, avisos y trámites sin urgencia.

La ortografía informal o las abreviaturas NO cambian la categoría ni la
prioridad: clasifica por el contenido, no por la redacción.
Usa null en las entidades que el correo no mencione. No inventes datos.
"""


def clasificar_con_llm(texto, modelo=MODELO, reintentos=2):
    """Pide el JSON al LLM y lo valida con Pydantic. Reintenta si es inválido.

    Devuelve (clasificación o None, respuesta cruda, latencia en ms).
    """
    mensajes = [{"role": "system", "content": PROMPT_CLASIFICACION},
                {"role": "user", "content": texto}]
    inicio, crudo = time.perf_counter(), ""
    for _ in range(reintentos + 1):
        try:
            crudo = ollama.chat(model=modelo, messages=mensajes,
                                format=Clasificacion.model_json_schema(),
                                options={"temperature": 0})["message"]["content"]
            valido = Clasificacion.model_validate_json(crudo).model_dump()
            return valido, crudo, (time.perf_counter() - inicio) * 1000
        except ValidationError as error:
            mensajes += [{"role": "assistant", "content": crudo},
                         {"role": "user", "content": f"JSON inválido: {error}. "
                          "Devuelve solo el JSON corregido."}]
        except Exception as error:          # Ollama apagado o modelo inexistente
            crudo = f"Error del LLM: {error}"
            break
    return None, crudo, (time.perf_counter() - inicio) * 1000


def fusionar(reglas, llm):
    """Si discrepan gana la prioridad más alta y se pide revisión humana."""
    if llm is None:                         # plan de respaldo: solo reglas
        return {**reglas, "origen": "reglas", "requiere_revision_humana": False}
    discrepan = (reglas["categoria"], reglas["prioridad"]) != (llm["categoria"], llm["prioridad"])
    nivel = PRIORIDADES.index
    gana = reglas if nivel(reglas["prioridad"]) > nivel(llm["prioridad"]) else llm
    entidades = {k: reglas["entidades"][k] or llm["entidades"].get(k)
                 for k in reglas["entidades"]}
    return {"categoria": gana["categoria"], "prioridad": gana["prioridad"],
            "entidades": entidades, "resumen": llm["resumen"],
            "origen": "hibrido", "requiere_revision_humana": discrepan}


def clasificar_hibrido(texto, modelo=MODELO, reintentos=2, usar_llm=True, bd=None):
    """Reglas + LLM. Si hay base de datos, registra la evaluación del LLM."""
    reglas = clasificar_por_reglas(texto)
    llm, crudo, ms = clasificar_con_llm(texto, modelo, reintentos) if usar_llm else (None, "", 0)
    resultado = fusionar(reglas, llm)
    resultado["detalle"] = (
        f"Reglas: {reglas['categoria']}/{reglas['prioridad']} · LLM: "
        + (f"{llm['categoria']}/{llm['prioridad']} ({ms / 1000:.1f} s)" if llm
           else "sin respuesta válida, se usaron las reglas"))
    if bd and usar_llm:
        coincide = llm and not resultado["requiere_revision_humana"]
        bd.guardar("evaluaciones_llm", {
            "prompt": texto, "respuesta": crudo, "modelo": modelo, "latencia_ms": ms,
            "coincidio_con_reglas": bool(coincide) if llm else None})
    return resultado


# ============================================================
# 4. EXPERIMENTO
# ============================================================

def evaluar_clasificadores(modelo=MODELO, progreso=None):
    """Compara reglas, LLM e híbrido sobre los correos etiquetados."""
    predichos = {"reglas": [], "llm": [], "hibrido": []}
    tiempos = {"reglas": 0.0, "llm": 0.0}
    for numero, (texto, _, _) in enumerate(CORREOS, 1):
        inicio = time.perf_counter()
        reglas = clasificar_por_reglas(texto)
        tiempos["reglas"] += (time.perf_counter() - inicio) * 1000
        llm, _, ms = clasificar_con_llm(texto, modelo)
        tiempos["llm"] += ms
        hibrido = fusionar(reglas, llm)
        predichos["reglas"].append((reglas["categoria"], reglas["prioridad"]))
        predichos["llm"].append((llm["categoria"], llm["prioridad"]) if llm else ("?", "?"))
        predichos["hibrido"].append((hibrido["categoria"], hibrido["prioridad"]))
        if progreso:
            progreso(numero, len(CORREOS))

    total = len(CORREOS)
    tiempos["hibrido"] = tiempos["reglas"] + tiempos["llm"]
    resultado = {"modelo": modelo, "correos": total, "metodos": {}}
    for metodo, lista in predichos.items():
        matriz = {real: dict.fromkeys(CATEGORIAS + ["?"], 0) for real in CATEGORIAS}
        for (_, categoria, _), (predicha, _) in zip(CORREOS, lista):
            matriz[categoria][predicha] += 1
        resultado["metodos"][metodo] = {
            "exactitud_categoria": sum(c[1] == p[0] for c, p in zip(CORREOS, lista)) / total,
            "exactitud_prioridad": sum(c[2] == p[1] for c, p in zip(CORREOS, lista)) / total,
            "latencia_media_ms": tiempos[metodo] / total,
            "matriz_confusion": matriz}
    return resultado


def texto_experimento(resultado):
    """Tabla de métricas y matrices de confusión en texto."""
    lineas = [f"Modelo: {resultado['modelo']}   Correos: {resultado['correos']}", "",
              f"{'Método':<9}{'Categoría':>10}{'Prioridad':>11}{'Latencia':>13}"]
    for metodo, m in resultado["metodos"].items():
        lineas.append(f"{metodo:<9}{m['exactitud_categoria']:>10.0%}"
                      f"{m['exactitud_prioridad']:>11.0%}{m['latencia_media_ms']:>10.0f} ms")
    for metodo, m in resultado["metodos"].items():
        lineas += ["", f"Matriz de confusión - {metodo} (fila: real, columna: predicho)",
                   " " * 22 + "".join(f"{c[:5]:>6}" for c in CATEGORIAS + ["?"])]
        lineas += [f"{real:<22}" + "".join(f"{n:>6}" for n in fila.values())
                   for real, fila in m["matriz_confusion"].items()]
    return "\n".join(lineas)


# ============================================================
# 5. ASISTENTE EXPLICATIVO (RAG SENCILLO)
# ============================================================
# Consulta primero, contexto después. Si MongoDB no devuelve registros
# NO se llama al LLM: se responde «No tengo información» directamente.

SIN_INFORMACION = "No tengo información sobre eso en la base de datos."

PROMPT_ASISTENTE = """
Eres el asistente del centro de control LogiSmart. Recibes REGISTROS
sacados de la base de datos y una PREGUNTA del operador.
1. Responde ÚNICAMENTE con lo que digan los registros.
2. Si preguntan qué pasó, cuáles o cuántos, resume lo que dicen los registros.
3. Si preguntan por qué se tomó una decisión, explica qué premisas la
   causaron y qué regla se aplicó.
4. Termina cada frase con la etiqueta de su fuente entre corchetes,
   copiada tal cual de los registros.
5. Solo si ningún registro tiene relación con la pregunta, responde
   "No tengo información."
6. No inventes datos. Responde en español en máximo 5 frases.
"""

# Cómo se resume cada registro para el LLM. El nombre del conductor no se
# incluye (privacidad). De la explicación del acceso solo van las reglas
# que se cumplieron.
FORMATO = {
    "camiones": lambda c: (
        f"Camión {c['camion_id']}, placa {c['placa']}, empresa {c['empresa']}, "
        f"autorización previa: {'sí' if c['autorizacion'] else 'no'}, certificación "
        f"vigente hasta {c['certificacion_vigente_hasta']:%Y-%m-%d}."),
    "accesos": lambda a: (
        f"Acceso de {a['camion_id'] or 'camión sin registro'} el "
        f"{a['creado_en']:%Y-%m-%d %H:%M}. Decisión: {a['decision']}. " + " ".join(
            paso for paso in a["explicacion"][1:] if "Falso" not in paso)),
    "incidentes": lambda i: (
        f"Incidente del {i['creado_en']:%Y-%m-%d}, categoría {i['categoria']}, "
        f"prioridad {i['prioridad']}, estado {i['estado']}: {i['resumen']}"),
    "riesgos_eticos": lambda r: (
        f"Riesgo en {r['modulo']}: {r['descripcion']} Puntaje inicial "
        f"{r['probabilidad'] * r['impacto']}, puntaje después de mitigar "
        f"{r['probabilidad_residual'] * r['impacto_residual']}. "
        f"Mitigación: {r['mitigacion']}"),
}
# Palabras de la pregunta que indican qué colección consultar.
TEMAS = {
    "camiones": "camion placa empresa flota unidad",
    "accesos": "acceso bitacora deneg negad inspeccion reten entr ingres semaforo decision",
    "incidentes": "incidente correo reporte abiert cerrad atencion",
    "riesgos_eticos": "riesgo mitigacion etic",
}


def recuperar_contexto(pregunta, bd):
    """Busca en MongoDB los registros relacionados con la pregunta."""
    plano = normalizar(pregunta)
    ids = [f"CAM-{n}" for n in re.findall(r"\bCAM[\s-]?(\d{3,6})\b", pregunta, re.I)]
    for placa in re.findall(r"\b(?!CAM)[A-Z]{3}-\d{3,4}\b", pregunta.upper()):
        ids += [c["camion_id"] for c in bd.listar("camiones", {"placa": placa})]

    registros = []                          # (colección, registro)
    for camion_id in dict.fromkeys(ids):    # pregunta sobre un camión concreto
        consultas = (("camiones", {"camion_id": camion_id}),
                     ("accesos", {"camion_id": camion_id}),
                     ("incidentes", {"datos_extraidos.camion_id": camion_id}))
        for coleccion, filtro in consultas:
            registros += [(coleccion, r) for r in bd.listar(coleccion, filtro, 3)]
    if not ids:                             # pregunta general: los más recientes
        # "denegados", "en inspección"... filtra los accesos por esa decisión
        decision = next((d for clave, d in (("deneg", "denegado"), ("negad", "denegado"),
                                            ("inspecc", "Inspección"), ("reten", "Retención"))
                         if clave in plano), None)
        for coleccion, palabras in TEMAS.items():
            if any(p in plano for p in palabras.split()):
                filtro = {"decision": {"$regex": decision}} \
                    if decision and coleccion == "accesos" else None
                encontrados = bd.listar(coleccion, filtro, 6)
                if coleccion == "riesgos_eticos":   # primero los de mayor puntaje
                    encontrados.sort(key=lambda r: -r["probabilidad"] * r["impacto"])
                registros += [(coleccion, r) for r in encontrados]

    cuenta, fuentes = {}, []
    for coleccion, registro in registros:   # etiquetas cortas: accesos-1, accesos-2...
        cuenta[coleccion] = cuenta.get(coleccion, 0) + 1
        fuentes.append(f"[{coleccion}-{cuenta[coleccion]}] {FORMATO[coleccion](registro)}")
    return fuentes


def responder(pregunta, bd, modelo=MODELO):
    """Devuelve (respuesta, fuentes consultadas)."""
    fuentes = recuperar_contexto(pregunta, bd)
    if not fuentes:
        return SIN_INFORMACION, []
    contenido = "REGISTROS:\n" + "\n".join(fuentes) + f"\n\nPREGUNTA: {pregunta}"
    try:
        respuesta = ollama.chat(model=modelo, options={"temperature": 0}, messages=[
            {"role": "system", "content": PROMPT_ASISTENTE},
            {"role": "user", "content": contenido}])["message"]["content"].strip()
    except Exception as error:
        return f"El LLM no está disponible ({error}). Revisa las fuentes.", fuentes
    # Control de alucinaciones: toda cita debe ser de una fuente entregada.
    etiquetas = {f.split("]")[0][1:] for f in fuentes}
    citas = set(re.findall(r"\b((?:camiones|accesos|incidentes|riesgos_eticos)-\d+)\b",
                           respuesta))
    if citas - etiquetas:
        respuesta += "\n\n⚠ Verifica esta respuesta: cita una fuente que no se consultó."
    elif not citas and "no tengo" not in respuesta.lower():
        respuesta += "\n\nFuentes: " + " ".join(f"[{e}]" for e in sorted(etiquetas))
    return respuesta, fuentes


if __name__ == "__main__":
    correo = CORREOS[1][0]
    print("Correo:", correo)
    print("Reglas:", clasificar_por_reglas(correo))
    print("Híbrido:", clasificar_hibrido(correo))
