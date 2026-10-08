import os
from datetime import datetime
from urllib.parse import quote_plus

import ollama
from pymongo import MongoClient

MODELO_POR_DEFECTO = "llama3.2"


def conectar_coleccion():
    """Colección de MongoDB Atlas donde se guardan las conversaciones.

    Los datos de conexión se leen del archivo .env de la carpeta del
    proyecto. Devuelve None si el archivo no existe.
    """
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    if not os.path.exists(ruta):
        return None
    env = dict(linea.strip().split("=", 1) for linea in open(ruta, encoding="utf-8")
               if "=" in linea and not linea.startswith("#"))
    uri = "mongodb+srv://{}:{}@{}/?retryWrites=true&w=majority".format(
        quote_plus(env["Mongo_User"]), quote_plus(env["Mongo_Password"]),
        env["Mongo_Cluster"])
    cliente = MongoClient(uri, serverSelectionTimeoutMS=8000)
    return cliente[env["Mongo_DB"]][env["Mongo_Colleccion"]]


MENSAJE_SISTEMA = """
Eres un entrenador de boxeo con experiencia que asiste a boxeadores
amateurs y profesionales, desde principiantes hasta competidores.

Debes:

1. Responder siempre en español, con tono motivador y directo.
2. Preguntar el nivel, peso y objetivo del boxeador cuando haga
   falta para personalizar el consejo.
3. Explicar la técnica paso a paso (guardia, desplazamientos, jab,
   cruzado, gancho, uppercut, defensa) y el porqué de cada detalle.
4. Proponer rutinas concretas: asaltos, tiempos, descansos y
   repeticiones (sombra, saco, manoplas, cuerda, físico).
5. Si el boxeador describe un error técnico, explicarle cómo
   corregirlo con ejercicios específicos.
6. Dar orientación general de nutrición, descanso y control de peso,
   desaconsejando los cortes de peso extremos y la deshidratación.
7. Priorizar la salud: recomendar protección adecuada y, ante golpes
   en la cabeza con mareo, dolor persistente o lesiones, indicar
   detener el entrenamiento y acudir a un médico. No diagnosticar.
8. No inventar datos; si no sabes algo, decirlo.
9. Respuestas breves (máximo 200 palabras) salvo que se pida detalle.
"""

MENSAJE_RESUMEN = """
Eres un asistente que resume conversaciones. Resume en español, en
máximo 6 viñetas, los temas tratados, las dudas del usuario y las
conclusiones o recomendaciones dadas. No agregues información nueva.
"""


class TutorLLM:
    """Mantiene el historial y conversa con el modelo."""

    def __init__(self, modelo=MODELO_POR_DEFECTO):
        self.modelo = modelo
        self.mensajes = [{"role": "system", "content": MENSAJE_SISTEMA}]
        self.conversacion = datetime.now().strftime("%Y%m%d-%H%M%S")
        try:
            self.coleccion = conectar_coleccion()
        except Exception:
            self.coleccion = None       # .env incompleto: no se guarda

    def guardar(self, tipo, pregunta, respuesta):
        """Guarda un registro en MongoDB. Si falla, el chat sigue funcionando."""
        if self.coleccion is None:
            return
        try:
            self.coleccion.insert_one({
                "conversacion": self.conversacion, "fecha": datetime.now(),
                "tipo": tipo, "modelo": self.modelo,
                "pregunta": pregunta, "respuesta": respuesta})
        except Exception:
            self.coleccion = None       # sin conexión: no reintentar en cada turno

    # --------------------------------------------------------
    def preguntar(self, texto):
        """Envía una pregunta y devuelve la respuesta.

        Si falla, el historial queda intacto y se propaga la excepción.
        """
        self.mensajes.append({"role": "user", "content": texto})
        try:
            respuesta = ollama.chat(model=self.modelo, messages=self.mensajes)
            contenido = respuesta["message"]["content"]
        except Exception:
            self.mensajes.pop()
            raise
        self.mensajes.append({"role": "assistant", "content": contenido})
        self.guardar("pregunta", texto, contenido)
        return contenido

    # --------------------------------------------------------
    def turnos(self):
        """Mensajes de usuario/asistente."""
        return [m for m in self.mensajes if m["role"] != "system"]

    def reiniciar(self):
        self.mensajes = self.mensajes[:1]
        self.conversacion = datetime.now().strftime("%Y%m%d-%H%M%S")

    # --------------------------------------------------------
    def resumen(self):
        """Resumen del historial: con el LLM y, si falla, uno local."""
        turnos = self.turnos()
        if not turnos:
            return "Aún no hay conversación que resumir."
        try:
            texto = self._resumen_llm(turnos)
        except Exception:
            return self._resumen_local(turnos)
        self.guardar("resumen", "Resumen del historial", texto)
        return texto

    def _resumen_llm(self, turnos):
        transcripcion = "\n".join(
            f"{'Boxeador' if m['role'] == 'user' else 'Entrenador'}: {m['content']}"
            for m in turnos
        )
        respuesta = ollama.chat(
            model=self.modelo,
            messages=[
                {"role": "system", "content": MENSAJE_RESUMEN},
                {"role": "user", "content": transcripcion},
            ],
        )
        return respuesta["message"]["content"].strip()

    @staticmethod
    def _resumen_local(turnos):
        """Respaldo sin LLM: lista las preguntas hechas."""
        preguntas = [m["content"] for m in turnos if m["role"] == "user"]
        lineas = ["(Resumen básico, el LLM no está disponible)",
                  f"Preguntas realizadas: {len(preguntas)}"]
        for i, p in enumerate(preguntas, 1):
            corto = p if len(p) <= 80 else p[:77] + "..."
            lineas.append(f"  {i}. {corto}")
        return "\n".join(lineas)

    # --------------------------------------------------------
    @staticmethod
    def modelos_disponibles():
        """Nombres de modelos instalados en Ollama ([] si no responde)."""
        try:
            return sorted(m["model"] for m in ollama.list()["models"])
        except Exception:
            return []


# Si se ejecuta este archivo directamente, abre la interfaz gráfica.
if __name__ == "__main__":
    from tutor_gui import main
    main()
