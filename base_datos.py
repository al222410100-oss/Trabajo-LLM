# ============================================================
# BASE DE DATOS - LOGISMART
# ============================================================
# Esquemas Pydantic, conexión a MongoDB, CRUD, agregación y reportes.

import csv
import json
import os
from datetime import datetime
from typing import Literal, Optional
from urllib.parse import quote_plus

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pymongo import MongoClient
from pymongo.errors import PyMongoError


def leer_env():
    """Lee el archivo .env (junto a este archivo) con los datos de conexión."""
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    datos = {}
    if os.path.exists(ruta):
        for linea in open(ruta, encoding="utf-8"):
            if "=" in linea and not linea.startswith("#"):
                clave, valor = linea.strip().split("=", 1)
                datos[clave.strip()] = valor.strip()
    return datos


ENV = leer_env()
if ENV.get("Mongo_Cluster"):                # MongoDB Atlas
    MONGO_URI = "mongodb+srv://{}:{}@{}/?retryWrites=true&w=majority".format(
        quote_plus(ENV["Mongo_User"]), quote_plus(ENV["Mongo_Password"]),
        ENV["Mongo_Cluster"])
else:                                       # sin .env: MongoDB local
    MONGO_URI = "mongodb://localhost:27017"
MONGO_DB = ENV.get("Mongo_DB", "logismart")
CATEGORIAS = ["acceso", "peso", "materiales_peligrosos", "documentacion",
              "seguridad", "mantenimiento", "otro"]
PRIORIDADES = ["baja", "media", "alta", "critica"]
ESTADOS = ["nuevo", "en_atencion", "cerrado"]


def ahora():
    return datetime.now().astimezone()


# ---------------- Esquemas (una clase por colección) ----------------

class Registro(BaseModel):
    creado_en: datetime = Field(default_factory=ahora)   # marca de tiempo


class Camion(Registro):
    camion_id: str = Field(pattern=r"^CAM-\d{3,6}$")
    placa: str = Field(min_length=5, max_length=10)
    empresa: str = Field(min_length=2)
    autorizacion: bool = False
    conductor: str = Field(min_length=2)          # dato personal
    certificacion_vigente_hasta: datetime
    certificacion_peligrosos: bool = False


class Acceso(Registro):
    camion_id: Optional[str] = None
    P: bool
    Q: bool
    R: bool
    S: bool
    V: bool = False
    H: bool = False
    A: bool
    E: bool
    D: bool = False
    T: bool = False
    decision: str
    semaforo: str
    explicacion: list[str]
    operador: str = Field(min_length=2)


class Entidades(BaseModel):
    camion_id: Optional[str] = None
    placa: Optional[str] = None
    empresa: Optional[str] = None


class Clasificacion(BaseModel):
    """Esquema exacto del JSON que debe devolver el LLM."""
    model_config = ConfigDict(extra="forbid")
    categoria: Literal[tuple(CATEGORIAS)]
    prioridad: Literal[tuple(PRIORIDADES)]
    entidades: Entidades = Entidades()
    resumen: str = Field(min_length=5, max_length=300)


class Incidente(Registro):
    correo_original: str = Field(min_length=10)
    categoria: Literal[tuple(CATEGORIAS)]
    prioridad: Literal[tuple(PRIORIDADES)]
    resumen: str = Field(min_length=5, max_length=300)
    origen: str = "hibrido"                      # reglas, hibrido o manual
    requiere_revision_humana: bool = False
    datos_extraidos: Entidades = Entidades()
    estado: Literal[tuple(ESTADOS)] = "nuevo"
    historial: list[str] = []


class RiesgoEtico(Registro):
    modulo: str = Field(min_length=2)
    descripcion: str = Field(min_length=5)
    categoria: str = Field(min_length=2)
    probabilidad: int = Field(ge=1, le=5)
    impacto: int = Field(ge=1, le=5)
    mitigacion: str = Field(min_length=5)
    probabilidad_residual: int = Field(ge=1, le=5)
    impacto_residual: int = Field(ge=1, le=5)
    historico: list[str] = []


class EvaluacionLLM(Registro):
    prompt: str
    respuesta: str
    modelo: str
    latencia_ms: float
    coincidio_con_reglas: Optional[bool] = None


MODELOS = {"camiones": Camion, "accesos": Acceso, "incidentes": Incidente,
           "riesgos_eticos": RiesgoEtico, "evaluaciones_llm": EvaluacionLLM}


# ---------------- Conexión y CRUD ----------------

class ErrorBaseDatos(Exception):
    """Error con un mensaje que se puede mostrar al usuario."""


def protegido(funcion):
    """Convierte los fallos de validación y de MongoDB en mensajes claros."""
    def envoltura(*args, **kwargs):
        try:
            return funcion(*args, **kwargs)
        except ValidationError as error:
            campos = ", ".join(str(e["loc"][0]) for e in error.errors())
            raise ErrorBaseDatos(f"Revisa estos datos, faltan o no son válidos: {campos}.")
        except PyMongoError:
            raise ErrorBaseDatos("No se pudo conectar con MongoDB. Verifica que "
                                 "el servicio esté iniciado.")
    return envoltura


class BaseDatos:
    def __init__(self, uri=MONGO_URI, nombre=MONGO_DB):
        self.cliente = MongoClient(uri, serverSelectionTimeoutMS=8000, tz_aware=True)
        self.db = self.cliente[nombre]

    def disponible(self):
        try:
            return bool(self.cliente.admin.command("ping"))
        except PyMongoError:
            return False

    @protegido
    def guardar(self, coleccion, datos, id=None):
        """Valida con Pydantic y crea el registro (o lo reemplaza si hay id)."""
        documento = MODELOS[coleccion](**datos).model_dump()
        if coleccion == "camiones":
            repetido = self.db.camiones.find_one({"camion_id": documento["camion_id"]})
            if repetido and str(repetido["_id"]) != id:
                raise ErrorBaseDatos("Ya existe un camión con ese identificador.")
        if id:
            self.db[coleccion].replace_one({"_id": ObjectId(id)}, documento)
            return id
        return str(self.db[coleccion].insert_one(documento).inserted_id)

    @protegido
    def listar(self, coleccion, filtro=None, limite=200):
        cursor = self.db[coleccion].find(filtro or {}).sort("creado_en", -1)
        return [{**d, "_id": str(d["_id"])} for d in cursor.limit(limite)]

    @protegido
    def contar(self, coleccion, filtro=None):
        return self.db[coleccion].count_documents(filtro or {})

    @protegido
    def eliminar(self, coleccion, id):
        self.db[coleccion].delete_one({"_id": ObjectId(id)})

    @protegido
    def incidentes_por_categoria_y_semana(self, desde=None, hasta=None):
        """Agregación: total de incidentes por semana ISO y categoría."""
        grupo = {"semana": {"$isoWeek": "$creado_en"}, "categoria": "$categoria"}
        etapas = [{"$match": rango(desde, hasta)},
                  {"$group": {"_id": grupo, "total": {"$sum": 1}}},
                  {"$sort": {"_id.semana": 1}}]
        return [{**d["_id"], "total": d["total"]}
                for d in self.db.incidentes.aggregate(etapas)]


def rango(desde=None, hasta=None):
    """Filtro de fechas para los indicadores del panel."""
    limites = {clave: valor for clave, valor in (("$gte", desde), ("$lt", hasta)) if valor}
    return {"creado_en": limites} if limites else {}


# ---------------- Exportación de reportes ----------------

def exportar(ruta, titulo, filas):
    """Exporta según la extensión del archivo: .json, .csv o .pdf."""
    if not filas:
        raise ErrorBaseDatos("No hay registros para exportar en este reporte.")
    columnas = [c for c in dict.fromkeys(c for fila in filas for c in fila) if c != "_id"]
    tabla = [columnas] + [[str(fila.get(c, "")) for c in columnas] for fila in filas]
    if ruta.endswith(".json"):
        with open(ruta, "w", encoding="utf-8") as archivo:
            json.dump(filas, archivo, indent=2, ensure_ascii=False, default=str)
    elif ruta.endswith(".csv"):
        with open(ruta, "w", encoding="utf-8-sig", newline="") as archivo:
            csv.writer(archivo).writerows(tabla)
    else:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import landscape, letter
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Table
        estilos = getSampleStyleSheet()
        chico = estilos["BodyText"].clone("chico", fontSize=6, leading=7)
        celdas = [[Paragraph(valor[:200].replace("<", "("), chico) for valor in fila[:8]]
                  for fila in tabla]
        cuadro = Table(celdas, repeatRows=1, colWidths=[720 / len(celdas[0])] * len(celdas[0]),
                       style=[("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                              ("BACKGROUND", (0, 0), (-1, 0), colors.lightblue)])
        pie = Paragraph(f"{ahora():%Y-%m-%d %H:%M} · {len(filas)} registros", estilos["Normal"])
        SimpleDocTemplate(ruta, pagesize=landscape(letter)).build(
            [Paragraph(titulo, estilos["Title"]), pie, cuadro])


if __name__ == "__main__":
    bd = BaseDatos()
    for nombre in MODELOS:
        print(nombre, bd.contar(nombre), "registros")
