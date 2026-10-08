# ============================================================
# LOGISMART PYTHON SUITE - INTERFAZ GRÁFICA (CustomTkinter)
# ============================================================
# Ejecutar:  python main.py

import random
import threading
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk
import ollama

import logica
from base_datos import (CATEGORIAS, ESTADOS, MODELOS, PRIORIDADES, BaseDatos,
                        ahora, exportar, rango)
from incidentes import (CORREOS, clasificar_hibrido, clasificar_por_reglas,
                        evaluar_clasificadores, responder, texto_experimento)
from peas import AgenteLogiSmart
from riesgos import cargar_riesgos_iniciales, nivel, puntajes
from tablas_verdad import tabla_verdad

COLORES = {"verde": "#0ca30c", "amarillo": "#fab219", "rojo": "#d03b3b"}
ACENTO, OSCURO, FONDO, SUAVE = "#0f766e", "#0b5a54", "#b00a0a", "#c9d0ce"
AJUSTES = {"modelo": "llama3.2", "umbral_critico": 15, "horario_inicio": 22,
           "horario_fin": 6, "modo_simulacion": False, "operador": "operador1"}


def texto(valor):
    """Convierte un valor de MongoDB en texto para tablas y formularios."""
    if isinstance(valor, bool):
        return "Sí" if valor else "No"
    if isinstance(valor, datetime):
        return valor.astimezone().strftime("%Y-%m-%d %H:%M")
    return "" if valor is None else str(valor)


def leer_fecha(cadena, nombre):
    try:
        return datetime.strptime(cadena.strip(), "%Y-%m-%d").astimezone()
    except ValueError:
        raise ValueError(f"«{nombre}» debe tener el formato AAAA-MM-DD, "
                         "por ejemplo 2026-10-07.") from None


def cargar_datos_demo(bd, ajustes):
    """Llena las colecciones vacías con datos ficticios."""
    if not bd.contar("camiones"):
        demo = [("CAM-101", "ABC-123", "Transportes Norte", True, 200, False),
                ("CAM-102", "DEF-456", "Logística Sur", True, 120, False),
                ("CAM-103", "GHI-321", "Químicos del Bajío", True, 300, True),
                ("CAM-104", "JKL-654", "Fletes del Centro", False, 90, False),
                ("CAM-105", "MNO-987", "Químicos del Bajío", True, 60, False),
                ("CAM-106", "PQR-246", "Transportes Norte", True, -30, False)]
        for n, (cid, placa, empresa, autorizado, dias, peligrosos) in enumerate(demo, 1):
            bd.guardar("camiones", {
                "camion_id": cid, "placa": placa, "empresa": empresa,
                "autorizacion": autorizado, "conductor": f"Conductor demo {n}",
                "certificacion_vigente_hasta": ahora() + timedelta(days=dias),
                "certificacion_peligrosos": peligrosos})
    if not bd.contar("accesos"):
        llegadas = [("CAM-101", 0, 0, 9), ("CAM-102", 1, 0, 11), ("CAM-103", 0, 1, 10),
                    ("CAM-104", 0, 0, 14), ("CAM-105", 0, 1, 16), ("CAM-103", 0, 1, 23),
                    ("CAM-106", 0, 0, 8), ("CAM-101", 1, 0, 12)]
        for dias, (cid, peso, peligrosos, hora) in enumerate(llegadas):
            camion = bd.listar("camiones", {"camion_id": cid})[0]
            momento = (ahora() - timedelta(days=dias)).replace(hour=hora, minute=15)
            premisas = logica.premisas_de_camion(
                camion, bool(peso), bool(peligrosos), momento,
                ajustes["horario_inicio"], ajustes["horario_fin"])
            bd.guardar("accesos", {**logica.evaluar(premisas), "camion_id": cid,
                                   "operador": "demo", "creado_en": momento})
    if not bd.contar("incidentes"):
        for n, (correo, _, _) in enumerate(CORREOS[::2]):
            r = clasificar_por_reglas(correo)
            bd.guardar("incidentes", {
                "correo_original": correo, "categoria": r["categoria"],
                "prioridad": r["prioridad"], "resumen": r["resumen"], "origen": "reglas",
                "datos_extraidos": r["entidades"], "estado": ESTADOS[n % 3],
                "historial": ["Creado con datos de demostración"],
                "creado_en": ahora() - timedelta(days=(n * 5) % 27)})
    cargar_riesgos_iniciales(bd)


class Crud(ctk.CTkFrame):
    """Tabla + formulario con Nuevo / Guardar / Eliminar para una colección.

    columnas: [(título, función(registro))]
    campos:   {clave: (etiqueta, tipo)}, con tipo "texto", "fecha", "si_no"
              o una lista de opciones.
    """

    def __init__(self, padre, app, coleccion, columnas, campos, preparar=None):
        super().__init__(padre, fg_color="transparent")
        self.app, self.coleccion, self.columnas = app, coleccion, columnas
        self.campos, self.preparar, self.actual, self.registros = campos, preparar, None, []
        self.tabla = app.tabla(self, [c[0] for c in columnas], 7)
        self.tabla.bind("<<TreeviewSelect>>", self.seleccionar)
        formulario = ctk.CTkFrame(self)
        formulario.pack(fill="x", pady=4)
        formulario.grid_columnconfigure((1, 3), weight=1)
        self.widgets = {}
        for n, (clave, (etiqueta, tipo)) in enumerate(campos.items()):
            fila, columna = divmod(n, 2)
            ctk.CTkLabel(formulario, text=etiqueta).grid(
                row=fila, column=columna * 2, sticky="w", padx=8, pady=3)
            if tipo == "si_no":
                widget = ctk.CTkSwitch(formulario, text="")
            elif isinstance(tipo, list):
                widget = ctk.CTkOptionMenu(formulario, values=tipo)
            else:
                widget = ctk.CTkEntry(formulario)
            widget.grid(row=fila, column=columna * 2 + 1, sticky="ew", padx=8, pady=3)
            self.widgets[clave] = widget
        botones = ctk.CTkFrame(self, fg_color="transparent")
        botones.pack(fill="x")
        if campos:
            ctk.CTkButton(botones, text="Nuevo", width=90, command=self.nuevo).pack(side="left", padx=3)
            ctk.CTkButton(botones, text="Guardar", width=90, command=self.guardar).pack(side="left", padx=3)
        ctk.CTkButton(botones, text="Eliminar", width=90, fg_color="#b03434",
                      command=self.eliminar).pack(side="left", padx=3)

    def refrescar(self):
        self.registros = self.app.bd.listar(self.coleccion)
        self.tabla.delete(*self.tabla.get_children())
        for r in self.registros:
            self.tabla.insert("", "end", iid=r["_id"],
                              values=[texto(funcion(r)) for _, funcion in self.columnas])

    def seleccionar(self, _=None):
        elegido = self.tabla.selection()
        self.actual = next((r for r in self.registros if elegido and r["_id"] == elegido[0]), None)
        for clave, widget in self.widgets.items():
            valor = self.actual.get(clave) if self.actual else None
            if isinstance(widget, ctk.CTkSwitch):
                widget.select() if valor else widget.deselect()
            elif isinstance(widget, ctk.CTkOptionMenu):
                widget.set(str(valor) if valor is not None else self.campos[clave][1][0])
            else:
                widget.delete(0, "end")
                widget.insert(0, texto(valor)[:10] if self.campos[clave][1] == "fecha" else texto(valor))

    def nuevo(self):
        self.tabla.selection_remove(self.tabla.selection())
        self.seleccionar()

    def leer(self):
        datos = {}
        for clave, (etiqueta, tipo) in self.campos.items():
            valor = self.widgets[clave].get()
            if tipo == "fecha":
                valor = leer_fecha(valor, etiqueta)
            elif tipo == "si_no":
                valor = bool(valor)
            elif isinstance(tipo, list) and valor.isdigit():
                valor = int(valor)
            datos[clave] = valor.strip() if isinstance(valor, str) else valor
        return datos

    def guardar(self):
        def accion():
            datos = {**(self.actual or {}), **self.leer()}
            if self.preparar:
                datos = self.preparar(datos, self.actual)
            self.app.bd.guardar(self.coleccion, datos, (self.actual or {}).get("_id"))
            self.app.refrescar()
        self.app.intentar(accion)

    def eliminar(self):
        if self.actual is None:
            return self.app.aviso("Selecciona un registro de la tabla.")
        if messagebox.askyesno("Eliminar", "¿Eliminar el registro seleccionado?"):
            self.app.intentar(lambda: (self.app.bd.eliminar(self.coleccion, self.actual["_id"]),
                                       self.app.refrescar()))


class LogiSmartApp(ctk.CTk):

    def __init__(self):
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("green")
        ctk.ThemeManager.theme["CTkFrame"]["fg_color"] = [SUAVE, SUAVE]
        ctk.ThemeManager.theme["CTkFrame"]["top_fg_color"] = ["#e3ebe8", "#e3ebe8"]
        for widget, clave, color in (              # color de acento en los controles
                ("CTkButton", "fg_color", ACENTO), ("CTkButton", "hover_color", OSCURO),
                ("CTkOptionMenu", "fg_color", ACENTO), ("CTkOptionMenu", "button_color", OSCURO),
                ("CTkOptionMenu", "button_hover_color", OSCURO),
                ("CTkSwitch", "progress_color", ACENTO),
                ("CTkSegmentedButton", "selected_color", ACENTO),
                ("CTkSegmentedButton", "selected_hover_color", OSCURO),
                ("CTkProgressBar", "progress_color", ACENTO)):
            ctk.ThemeManager.theme[widget][clave] = [color, color]
        super().__init__(fg_color=FONDO)
        self.title("LogiSmart - Centro de control de acceso")
        self.geometry("1320x820")
        self.bd = BaseDatos()
        self.ajustes = dict(AJUSTES)
        try:
            self.ajustes.update(self.bd.db.configuracion.find_one({"_id": "app"}) or {})
        except Exception:
            pass                            # sin MongoDB se usan los ajustes de fábrica
        self.incidente, self.experimento, self.progreso = None, None, ""

        estilo = ttk.Style(self)
        estilo.theme_use("clam")
        estilo.configure("Treeview", background=FONDO, fieldbackground=FONDO,
                         foreground="#1f2937", rowheight=int(26 * self._get_window_scaling()))
        estilo.configure("Treeview.Heading", background="#e3ebe8", foreground="#1f2937",
                         relief="flat")
        estilo.map("Treeview", background=[("selected", ACENTO)],
                   foreground=[("selected", "#ffffff")])
        estilo.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])

        # Menú lateral a la izquierda; a la derecha, título, página y barra de estado
        lateral = ctk.CTkFrame(self, width=230, corner_radius=0)
        lateral.pack(side="left", fill="y")
        lateral.pack_propagate(False)
        ctk.CTkLabel(lateral, text="LogiSmart", font=("Segoe UI", 26, "bold"),
                     text_color=ACENTO).pack(anchor="w", padx=22, pady=(26, 0))
        ctk.CTkLabel(lateral, text="Centro de control de acceso",
                     text_color="gray40").pack(anchor="w", padx=22, pady=(0, 22))
        derecha = ctk.CTkFrame(self, fg_color=FONDO, corner_radius=0)
        derecha.pack(side="left", fill="both", expand=True)
        pie = ctk.CTkFrame(derecha, corner_radius=0)
        pie.pack(side="bottom", fill="x")
        self.estado = ctk.CTkLabel(pie, text="Listo")
        self.estado.pack(side="left", padx=16, pady=3)
        self.spinner = ctk.CTkProgressBar(pie, mode="indeterminate", width=160)
        self.titulo = ctk.CTkLabel(derecha, text="", anchor="w", font=("Segoe UI", 22, "bold"))
        self.titulo.pack(fill="x", padx=22, pady=(18, 4))
        self.paginas, self.botones = {}, {}
        for nombre, construir in (
                ("Panel de control", self.tab_panel), ("Control de acceso", self.tab_acceso),
                ("Simulador", self.tab_simulador), ("Bandeja de incidentes", self.tab_bandeja),
                ("Asistente", self.tab_asistente), ("Riesgos éticos", self.tab_riesgos),
                ("Reportes", self.tab_reportes), ("Configuración", self.tab_config)):
            self.paginas[nombre] = ctk.CTkFrame(derecha, fg_color=FONDO, corner_radius=0)
            construir(self.paginas[nombre])
            self.botones[nombre] = ctk.CTkButton(
                lateral, text=nombre, anchor="w", height=40, hover_color="#d5e3df",
                command=lambda n=nombre: self.mostrar(n))
            self.botones[nombre].pack(fill="x", padx=12, pady=2)
        self.mostrar("Panel de control")
        self.after(200, self.refrescar)

    def mostrar(self, nombre):
        """Cambia de página y resalta su botón en el menú lateral."""
        for otro, pagina in self.paginas.items():
            pagina.pack_forget()
            activo = otro == nombre
            self.botones[otro].configure(fg_color=ACENTO if activo else "transparent",
                                         hover_color=OSCURO if activo else "#d5e3df",
                                         text_color="#ffffff" if activo else "#1f2937")
        self.paginas[nombre].pack(fill="both", expand=True, padx=12, pady=(0, 8))
        self.titulo.configure(text=nombre)

    # ---------------- Utilidades ----------------
    def aviso(self, mensaje):
        self.estado.configure(text=mensaje)

    def intentar(self, funcion):
        """Ejecuta una acción; si falla muestra un mensaje claro, no una traza."""
        try:
            return funcion()
        except Exception as error:
            self.aviso("Error: " + str(error).splitlines()[0])
            messagebox.showerror("No se pudo completar", str(error), parent=self)

    def en_hilo(self, funcion, al_terminar, mensaje):
        """Ejecuta una tarea lenta (LLM) sin congelar la ventana, con spinner."""
        caja = {}

        def trabajo():
            try:
                caja["resultado"] = funcion()
            except Exception as error:
                caja["error"] = error

        def revisar():
            if not caja:
                self.aviso(f"{mensaje} {self.progreso}")
                return self.after(150, revisar)
            self.spinner.stop()
            self.spinner.pack_forget()
            self.aviso("Listo")
            if "error" in caja:
                messagebox.showerror("No se pudo completar", str(caja["error"]), parent=self)
            else:
                al_terminar(caja["resultado"])

        self.progreso = ""
        self.spinner.pack(side="right", padx=16)
        self.spinner.start()
        threading.Thread(target=trabajo, daemon=True).start()
        revisar()

    def tabla(self, padre, columnas, alto=10):
        tabla = ttk.Treeview(padre, columns=columnas, show="headings", height=alto)
        for columna in columnas:
            tabla.heading(columna, text=columna)
            tabla.column(columna, width=90, anchor="w")
        tabla.pack(fill="both", expand=True, pady=4)
        return tabla

    def caja(self, padre, alto=120, expandir=True):
        caja = ctk.CTkTextbox(padre, wrap="word", height=alto)
        caja.pack(fill="both", expand=expandir, padx=8, pady=4)
        return caja

    def campo(self, padre, etiqueta, valor="", ancho=160):
        fila = ctk.CTkFrame(padre, fg_color="transparent")
        fila.pack(fill="x", padx=8, pady=3)
        ctk.CTkLabel(fila, text=etiqueta, width=230, anchor="w").pack(side="left")
        entrada = ctk.CTkEntry(fila, width=ancho)
        entrada.insert(0, str(valor))
        entrada.pack(side="left")
        return entrada

    @staticmethod
    def escribir(caja, contenido):
        caja.delete("1.0", "end")
        caja.insert("1.0", contenido)

    @staticmethod
    def semaforo(lienzo, color):
        lienzo.delete("all")
        for n, nombre in enumerate(("rojo", "amarillo", "verde")):
            lienzo.create_oval(8, 8 + n * 46, 48, 48 + n * 46, outline="",
                               fill=COLORES[nombre] if nombre == color else "#3a3a38")

    def refrescar(self):
        if not self.bd.disponible():
            return self.aviso("Sin conexión con MongoDB: inicia el servicio y vuelve a intentar.")
        self.intentar(lambda: (self.refrescar_panel(), self.crud_camiones.refrescar(),
                               self.crud_accesos.refrescar(), self.refrescar_incidentes(),
                               self.crud_riesgos.refrescar()))

    # ---------------- 1. Panel de control ----------------
    def tab_panel(self, tab):
        filtros = ctk.CTkFrame(tab)
        filtros.pack(fill="x", padx=8, pady=6)
        self.desde = ctk.CTkEntry(filtros, width=130, placeholder_text="Desde AAAA-MM-DD")
        self.hasta = ctk.CTkEntry(filtros, width=130, placeholder_text="Hasta AAAA-MM-DD")
        self.desde.pack(side="left", padx=8, pady=8)
        self.hasta.pack(side="left")
        ctk.CTkButton(filtros, text="Aplicar filtro", width=110,
                      command=lambda: self.intentar(self.refrescar_panel)).pack(side="left", padx=8)
        tarjetas = ctk.CTkFrame(tab, fg_color="transparent")
        tarjetas.pack(fill="x", padx=4)
        self.kpi = {}
        for titulo in ("Camiones atendidos", "Incidentes abiertos", "Riesgos críticos"):
            tarjeta = ctk.CTkFrame(tarjetas)
            tarjeta.pack(side="left", fill="x", expand=True, padx=4)
            ctk.CTkLabel(tarjeta, text=titulo).pack(anchor="w", padx=16, pady=(10, 0))
            self.kpi[titulo] = ctk.CTkLabel(tarjeta, text="–", font=("Segoe UI", 34, "bold"))
            self.kpi[titulo].pack(anchor="w", padx=16, pady=(0, 10))
        self.resumen_semanal = ctk.CTkTextbox(tab, wrap="word")
        self.resumen_semanal.pack(fill="both", expand=True, padx=8, pady=6)

    def refrescar_panel(self):
        desde = leer_fecha(self.desde.get(), "Desde") if self.desde.get().strip() else None
        hasta = leer_fecha(self.hasta.get(), "Hasta") + timedelta(days=1) \
            if self.hasta.get().strip() else None
        periodo = rango(desde, hasta)
        riesgos = self.bd.listar("riesgos_eticos", periodo)
        self.kpi["Camiones atendidos"].configure(text=self.bd.contar("accesos", periodo))
        self.kpi["Incidentes abiertos"].configure(
            text=self.bd.contar("incidentes", {**periodo, "estado": {"$ne": "cerrado"}}))
        self.kpi["Riesgos críticos"].configure(
            text=sum(puntajes(r)[1] >= self.ajustes["umbral_critico"] for r in riesgos))

        filas = self.bd.incidentes_por_categoria_y_semana(desde, hasta)    # agregación
        semanas = sorted({f["semana"] for f in filas})
        lineas = [f"Semana {s}:  " + ",  ".join(f"{f['categoria']} {f['total']}"
                                                 for f in filas if f["semana"] == s)
                  for s in semanas]
        self.escribir(self.resumen_semanal, "Incidentes por categoría y semana\n\n"
                      + ("\n".join(lineas) or "Sin incidentes en el periodo seleccionado."))

    # ---------------- 2. Control de acceso ----------------
    def tab_acceso(self, tab):
        izq = ctk.CTkFrame(tab)
        izq.pack(side="left", fill="y", padx=6, pady=6)
        self.buscar = ctk.CTkEntry(izq, width=300, placeholder_text="Placa o CAM-000 (vacío = manual)")
        self.buscar.pack(padx=8, pady=8)
        self.vars_acceso = {}
        for letra, nombre in logica.PREMISAS.items():
            self.vars_acceso[letra] = tk.BooleanVar()
            ctk.CTkSwitch(izq, text=f"{letra} — {nombre}", variable=self.vars_acceso[letra]
                          ).pack(anchor="w", padx=8, pady=3)
        self.operador = self.campo(izq, "Operador", self.ajustes["operador"], 120)
        ctk.CTkButton(izq, text="Evaluar y registrar", command=self.evaluar_acceso
                      ).pack(fill="x", padx=8, pady=8)
        self.luz_acceso = tk.Canvas(izq, width=56, height=148, bg="#1f1f1f", highlightthickness=0)
        self.luz_acceso.pack()
        self.decision = ctk.CTkLabel(izq, text="Sin evaluar", font=("Segoe UI", 17, "bold"))
        self.decision.pack(pady=4)
        self.explicacion = self.caja(izq, 200)
        self.semaforo(self.luz_acceso, None)

        der = ctk.CTkTabview(tab)
        der.pack(side="left", fill="both", expand=True, padx=6)
        self.crud_camiones = Crud(
            der.add("Camiones"), self, "camiones",
            [("ID", lambda c: c["camion_id"]), ("Placa", lambda c: c["placa"]),
             ("Empresa", lambda c: c["empresa"]), ("Autorizado", lambda c: c["autorizacion"]),
             ("Cert. hasta", lambda c: texto(c["certificacion_vigente_hasta"])[:10]),
             ("Mat. peligrosos", lambda c: c["certificacion_peligrosos"])],
            {"camion_id": ("ID (CAM-000)", "texto"), "placa": ("Placa", "texto"),
             "empresa": ("Empresa", "texto"), "conductor": ("Conductor", "texto"),
             "certificacion_vigente_hasta": ("Certificación vigente hasta", "fecha"),
             "autorizacion": ("Autorización previa", "si_no"),
             "certificacion_peligrosos": ("Cert. materiales peligrosos", "si_no")})
        self.crud_camiones.pack(fill="both", expand=True)
        self.crud_accesos = Crud(
            der.add("Bitácora de accesos"), self, "accesos",
            [("Fecha", lambda a: a["creado_en"]), ("Camión", lambda a: a["camion_id"] or "manual"),
             ("P Q R S V H", lambda a: " ".join(str(int(a[p])) for p in "PQRSVH")),
             ("A E T D", lambda a: " ".join(str(int(a[p])) for p in "AETD")),
             ("Decisión", lambda a: a["decision"]), ("Operador", lambda a: a["operador"])], {})
        self.crud_accesos.pack(fill="both", expand=True)

    def evaluar_acceso(self):
        def accion():
            buscado = self.buscar.get().strip().upper()
            premisas = {letra: var.get() for letra, var in self.vars_acceso.items()}
            camion = None
            if buscado:                     # P, S, V y H salen de los datos del camión
                encontrados = self.bd.listar("camiones", {"$or": [{"placa": buscado},
                                                                   {"camion_id": buscado}]})
                if not encontrados:
                    raise ValueError(f"No hay ningún camión con placa o ID «{buscado}».")
                camion = encontrados[0]
                premisas = logica.premisas_de_camion(
                    camion, premisas["Q"], premisas["R"], ahora(),
                    self.ajustes["horario_inicio"], self.ajustes["horario_fin"])
                for letra, valor in premisas.items():
                    self.vars_acceso[letra].set(valor)
            resultado = logica.evaluar(premisas)
            self.bd.guardar("accesos", {**resultado, "operador": self.operador.get().strip(),
                                        "camion_id": camion and camion["camion_id"]})
            self.semaforo(self.luz_acceso, resultado["semaforo"])
            self.decision.configure(text=resultado["decision"])
            self.escribir(self.explicacion, "\n\n".join(resultado["explicacion"]))
            self.refrescar()
        self.intentar(accion)

    # ---------------- 3. Simulador ----------------
    def tab_simulador(self, tab):
        izq = ctk.CTkFrame(tab)
        izq.pack(side="left", fill="y", padx=6, pady=6)
        self.vars_sim = {}
        for letra, nombre in logica.PREMISAS.items():
            self.vars_sim[letra] = tk.BooleanVar(value=letra in "PS")
            ctk.CTkSwitch(izq, text=f"{letra} — {nombre}", variable=self.vars_sim[letra],
                          command=self.simular).pack(anchor="w", padx=10, pady=4)
        self.salidas = {}
        for clave, nombre, formula, _, _ in logica.REGLAS:
            self.salidas[clave] = ctk.CTkLabel(izq, corner_radius=8, anchor="w", width=330)
            self.salidas[clave].pack(padx=10, pady=3)
        self.luz_sim = tk.Canvas(izq, width=56, height=148, bg="#1f1f1f", highlightthickness=0)
        self.luz_sim.pack(pady=8)
        self.decision_sim = ctk.CTkLabel(izq, text="", font=("Segoe UI", 16, "bold"))
        self.decision_sim.pack()

        centro = ctk.CTkFrame(tab)
        centro.pack(side="left", fill="both", expand=True, pady=6)
        encabezados, filas = tabla_verdad()
        self.tabla_sim = self.tabla(centro, encabezados, 20)
        for n, fila in enumerate(filas):
            self.tabla_sim.insert("", "end", iid=str(n), values=fila)
            self.tabla_sim.column(encabezados[0], width=40)
        der = ctk.CTkFrame(tab)
        der.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        self.explicacion_sim = self.caja(der, 300)
        analisis = self.caja(der, 200)
        analisis.insert("1.0", "REGLAS BASE (A, E)\n" + "\n".join(logica.analizar(logica.REGLAS_BASE))
                        + "\n\nTODAS LAS REGLAS\n" + "\n".join(logica.analizar()))
        self.simular()

    def simular(self):
        valores = {letra: var.get() for letra, var in self.vars_sim.items()}
        resultado = logica.evaluar(valores)
        for clave, nombre, formula, _, _ in logica.REGLAS:
            self.salidas[clave].configure(
                text=f"  {clave} = {int(resultado[clave])}    {nombre}:  {formula}",
                fg_color=ACENTO if resultado[clave] else "#e3ebe8",
                text_color="#ffffff" if resultado[clave] else "#1f2937")
        self.semaforo(self.luz_sim, resultado["semaforo"])
        self.decision_sim.configure(text=resultado["decision"])
        self.escribir(self.explicacion_sim, "\n\n".join(resultado["explicacion"]))
        fila = str(int("".join(str(int(valores[p])) for p in logica.PREMISAS), 2))
        self.tabla_sim.selection_set(fila)     # resalta la fila actual de la tabla
        self.tabla_sim.see(fila)

    # ---------------- 4. Bandeja de incidentes ----------------
    def tab_bandeja(self, tab):
        izq = ctk.CTkFrame(tab)
        izq.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        self.correo = self.caja(izq, 110, False)
        botones = ctk.CTkFrame(izq, fg_color="transparent")
        botones.pack(fill="x", padx=8)
        ctk.CTkButton(botones, text="Correo de ejemplo", command=lambda: self.escribir(
            self.correo, random.choice(CORREOS)[0])).pack(side="left")
        self.boton_clasificar = ctk.CTkButton(botones, text="Clasificar", command=self.clasificar)
        self.boton_clasificar.pack(side="left", padx=6)
        self.detalle = ctk.CTkLabel(izq, text="", wraplength=560, justify="left")
        self.detalle.pack(anchor="w", padx=8, pady=4)
        fila = ctk.CTkFrame(izq, fg_color="transparent")
        fila.pack(fill="x", padx=8)
        self.categoria = ctk.CTkOptionMenu(fila, values=CATEGORIAS)
        self.prioridad = ctk.CTkOptionMenu(fila, values=PRIORIDADES)
        self.estado_incidente = ctk.CTkOptionMenu(fila, values=ESTADOS)
        for widget in (self.categoria, self.prioridad, self.estado_incidente):
            widget.pack(side="left", padx=(0, 6))
        self.resumen = self.campo(izq, "Resumen", ancho=330)
        self.camion_incidente = self.campo(izq, "Camión mencionado")
        botones = ctk.CTkFrame(izq, fg_color="transparent")
        botones.pack(fill="x", padx=8, pady=4)
        ctk.CTkButton(botones, text="Guardar", command=self.guardar_incidente).pack(side="left")
        ctk.CTkButton(botones, text="Eliminar", fg_color="#b03434",
                      command=self.eliminar_incidente).pack(side="left", padx=6)
        ctk.CTkLabel(izq, text="Historial").pack(anchor="w", padx=8)
        self.historial = self.caja(izq, 120)
        der = ctk.CTkFrame(tab)
        der.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        self.tabla_incidentes = self.tabla(
            der, ["Fecha", "Categoría", "Prioridad", "Estado", "Revisión", "Resumen"], 24)
        self.tabla_incidentes.bind("<<TreeviewSelect>>", self.ver_incidente)

    def refrescar_incidentes(self):
        self.incidentes = self.bd.listar("incidentes")
        self.tabla_incidentes.delete(*self.tabla_incidentes.get_children())
        for i in self.incidentes:
            self.tabla_incidentes.insert("", "end", iid=i["_id"], values=(
                texto(i["creado_en"]), i["categoria"], i["prioridad"], i["estado"],
                "Sí" if i["requiere_revision_humana"] else "", i["resumen"]))

    def mostrar_incidente(self, incidente):
        self.incidente = incidente
        self.escribir(self.correo, incidente["correo_original"])
        self.categoria.set(incidente["categoria"])
        self.prioridad.set(incidente["prioridad"])
        self.estado_incidente.set(incidente.get("estado", "nuevo"))
        for entrada, valor in ((self.resumen, incidente["resumen"]),
                               (self.camion_incidente, incidente["datos_extraidos"]["camion_id"])):
            entrada.delete(0, "end")
            entrada.insert(0, valor or "")
        self.escribir(self.historial, "\n".join(incidente.get("historial", [])))

    def ver_incidente(self, _=None):
        elegido = self.tabla_incidentes.selection()
        if elegido:
            self.mostrar_incidente(next(i for i in self.incidentes if i["_id"] == elegido[0]))
            self.detalle.configure(text="Origen de la clasificación: " + self.incidente["origen"])

    def clasificar(self):
        correo = self.correo.get("1.0", "end").strip()
        if len(correo) < 10:
            return messagebox.showwarning("Correo vacío", "Pega el texto del correo "
                                          "(mínimo 10 caracteres).", parent=self)
        self.boton_clasificar.configure(state="disabled")
        ajustes = self.ajustes

        def listo(r):
            self.boton_clasificar.configure(state="normal")
            revision = "  ⚠ REQUIERE REVISIÓN HUMANA" if r["requiere_revision_humana"] else ""
            self.detalle.configure(text=r["detalle"] + revision)
            self.mostrar_incidente({
                "correo_original": correo, "categoria": r["categoria"],
                "prioridad": r["prioridad"], "resumen": r["resumen"], "origen": r["origen"],
                "requiere_revision_humana": r["requiere_revision_humana"],
                "datos_extraidos": r["entidades"], "estado": "nuevo",
                "historial": [f"{texto(ahora())} clasificado ({r['origen']})"]})
        self.en_hilo(lambda: clasificar_hibrido(
            correo, ajustes["modelo"], usar_llm=not ajustes["modo_simulacion"], bd=self.bd),
            listo, "Clasificando el correo con reglas y LLM...")

    def guardar_incidente(self):
        def accion():
            if self.incidente is None:
                raise ValueError("Primero clasifica un correo o selecciona un incidente.")
            i = self.incidente
            nuevos = {"categoria": self.categoria.get(), "prioridad": self.prioridad.get(),
                      "estado": self.estado_incidente.get(), "resumen": self.resumen.get().strip()}
            if (nuevos["categoria"], nuevos["prioridad"]) != (i["categoria"], i["prioridad"]):
                nuevos.update(origen="manual", requiere_revision_humana=False)
            cambios = ", ".join(f"{k}: {v}" for k, v in nuevos.items() if i.get(k) != v and k != "resumen")
            if cambios:
                i["historial"] = i["historial"] + [f"{texto(ahora())} {cambios}"]
            i["datos_extraidos"]["camion_id"] = self.camion_incidente.get().strip() or None
            i.update(nuevos)
            i["_id"] = self.bd.guardar("incidentes", i, i.get("_id"))
            self.refrescar()
            self.mostrar_incidente(i)
        self.intentar(accion)

    def eliminar_incidente(self):
        if self.incidente and self.incidente.get("_id") and messagebox.askyesno(
                "Eliminar", "¿Eliminar este incidente?"):
            self.intentar(lambda: self.bd.eliminar("incidentes", self.incidente["_id"]))
            self.incidente = None
            self.refrescar()

    # ---------------- 5. Asistente ----------------
    def tab_asistente(self, tab):
        izq = ctk.CTkFrame(tab)
        izq.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        self.chat = self.caja(izq, 400)
        self.chat.insert("end", "ASISTENTE: Pregúntame por un camión, por ejemplo: "
                         "¿por qué CAM-102 fue enviado a inspección?\n\n")
        self.pregunta = ctk.CTkEntry(izq, placeholder_text="Escribe tu pregunta y pulsa Enter")
        self.pregunta.pack(fill="x", padx=8, pady=8)
        self.pregunta.bind("<Return>", lambda e: self.preguntar())
        der = ctk.CTkFrame(tab)
        der.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        ctk.CTkLabel(der, text="Fuentes consultadas en MongoDB").pack(anchor="w", padx=8)
        self.fuentes = self.caja(der, 400)

    def preguntar(self):
        pregunta = self.pregunta.get().strip()
        if len(pregunta) < 3 or self.pregunta.cget("state") == "disabled":
            return
        self.pregunta.delete(0, "end")
        self.pregunta.configure(state="disabled")
        self.chat.insert("end", f"TÚ: {pregunta}\n\n")

        def listo(salida):
            respuesta, fuentes = salida
            self.pregunta.configure(state="normal")
            self.chat.insert("end", f"ASISTENTE: {respuesta}\n\n")
            self.chat.see("end")
            self.escribir(self.fuentes, "\n\n".join(fuentes) or "No se encontraron registros "
                          "relacionados; por eso el asistente no respondió con datos.")
        self.en_hilo(lambda: responder(pregunta, self.bd, self.ajustes["modelo"]), listo,
                     "Consultando MongoDB y redactando la respuesta...")

    # ---------------- 6. Riesgos éticos ----------------
    def tab_riesgos(self, tab):
        escala = ["1", "2", "3", "4", "5"]
        self.crud_riesgos = Crud(
            tab, self, "riesgos_eticos",
            [("Módulo", lambda r: r["modulo"]), ("Categoría", lambda r: r["categoria"]),
             ("Antes", lambda r: puntajes(r)[0]), ("Después", lambda r: puntajes(r)[1]),
             ("Nivel residual", lambda r: nivel(puntajes(r)[1])),
             ("Histórico", lambda r: len(r["historico"]))],
            {"modulo": ("Módulo", "texto"), "categoria": ("Categoría", "texto"),
             "descripcion": ("Descripción", "texto"), "mitigacion": ("Mitigación", "texto"),
             "probabilidad": ("Probabilidad (1-5)", escala), "impacto": ("Impacto (1-5)", escala),
             "probabilidad_residual": ("Probabilidad residual", escala),
             "impacto_residual": ("Impacto residual", escala)}, self.preparar_riesgo)
        self.crud_riesgos.pack(fill="both", expand=True, padx=6)

    @staticmethod
    def preparar_riesgo(datos, anterior):
        """Al editar, guarda en el histórico la evaluación anterior."""
        if puntajes(datos)[1] > puntajes(datos)[0]:
            raise ValueError("El riesgo residual no puede ser mayor que el inicial.")
        if anterior:
            antes, despues = puntajes(anterior)
            datos["historico"] = anterior["historico"] + [
                f"{texto(ahora())}: puntaje {antes} → {despues}"]
        return datos

    # ---------------- 7. Reportes ----------------
    def tab_reportes(self, tab):
        izq = ctk.CTkFrame(tab)
        izq.pack(side="left", fill="y", padx=6, pady=6)
        self.reporte = ctk.CTkOptionMenu(izq, width=260, values=list(MODELOS) + [
            "incidentes por categoría y semana", "experimento de clasificación"])
        self.reporte.pack(padx=10, pady=10)
        for formato in ("pdf", "csv", "json"):
            ctk.CTkButton(izq, text=f"Exportar a {formato.upper()}",
                          command=lambda f=formato: self.exportar(f)).pack(fill="x", padx=10, pady=4)
        der = ctk.CTkFrame(tab)
        der.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        ctk.CTkButton(der, text=f"Ejecutar experimento ({len(CORREOS)} correos etiquetados)",
                      command=self.ejecutar_experimento).pack(anchor="w", padx=8, pady=8)
        self.salida_experimento = self.caja(der, 400)
        self.salida_experimento.configure(font=("Consolas", 12), wrap="none")

    def exportar(self, formato):
        def accion():
            nombre = self.reporte.get()
            if nombre.startswith("experimento"):
                if not self.experimento:
                    raise ValueError("Primero ejecuta el experimento de clasificación.")
                filas = [{"metodo": m, **d} for m, d in self.experimento["metodos"].items()]
            elif nombre.startswith("incidentes por"):
                filas = self.bd.incidentes_por_categoria_y_semana()
            else:
                filas = self.bd.listar(nombre, limite=1000)
            ruta = filedialog.asksaveasfilename(
                defaultextension=f".{formato}", initialfile=f"{nombre.replace(' ', '_')}.{formato}")
            if ruta:
                exportar(ruta, f"LogiSmart - {nombre}", filas)
                self.aviso(f"Reporte exportado ({len(filas)} registros): {ruta}")
        self.intentar(accion)

    def ejecutar_experimento(self):
        def avance(hecho, total):
            self.progreso = f"{hecho}/{total}"

        def listo(resultado):
            self.experimento = resultado
            self.escribir(self.salida_experimento, texto_experimento(resultado))
        self.en_hilo(lambda: evaluar_clasificadores(self.ajustes["modelo"], avance), listo,
                     "Ejecutando el experimento...")

    # ---------------- 8. Configuración ----------------
    def tab_config(self, tab):
        izq = ctk.CTkFrame(tab)
        izq.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        try:
            modelos = sorted(m["model"] for m in ollama.list()["models"])
        except Exception:
            modelos = [self.ajustes["modelo"]]      # Ollama apagado
        fila = ctk.CTkFrame(izq, fg_color="transparent")
        fila.pack(fill="x", padx=8, pady=8)
        ctk.CTkLabel(fila, text="Modelo de Ollama", width=230, anchor="w").pack(side="left")
        self.modelo = ctk.CTkComboBox(fila, values=modelos, width=200)
        self.modelo.set(self.ajustes["modelo"])
        self.modelo.pack(side="left")
        self.entradas_config = {
            "umbral_critico": self.campo(izq, "Umbral de riesgo crítico (1-25)",
                                         self.ajustes["umbral_critico"]),
            "horario_inicio": self.campo(izq, "Horario restringido: inicio (0-23)",
                                         self.ajustes["horario_inicio"]),
            "horario_fin": self.campo(izq, "Horario restringido: fin (0-23)",
                                      self.ajustes["horario_fin"])}
        self.operador_config = self.campo(izq, "Operador por defecto", self.ajustes["operador"])
        self.simulacion = tk.BooleanVar(value=self.ajustes["modo_simulacion"])
        ctk.CTkSwitch(izq, variable=self.simulacion, text="Modo simulación de correos "
                      "(clasifica solo con reglas, sin LLM)").pack(anchor="w", padx=8, pady=8)
        ctk.CTkButton(izq, text="Guardar configuración", command=self.guardar_config
                      ).pack(anchor="w", padx=8, pady=4)
        ctk.CTkButton(izq, text="Cargar datos de demostración", command=lambda: self.intentar(
            lambda: (cargar_datos_demo(self.bd, self.ajustes), self.refrescar()))
            ).pack(anchor="w", padx=8, pady=4)
        der = ctk.CTkFrame(tab)
        der.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        agente = AgenteLogiSmart()
        self.caja(der, 400).insert("1.0", "MODELO PEAS DEL AGENTE\n\n" + "\n\n".join(
            f"{titulo}\n" + "\n".join(f"  • {e}" for e in lista) for titulo, lista in (
                ("Performance", agente.performance), ("Environment", agente.environment),
                ("Actuators", agente.actuators), ("Sensors", agente.sensors))))

    def guardar_config(self):
        def accion():
            limites = {"umbral_critico": (1, 25), "horario_inicio": (0, 23), "horario_fin": (0, 23)}
            for clave, entrada in self.entradas_config.items():
                valor, (minimo, maximo) = entrada.get().strip(), limites[clave]
                if not valor.isdigit() or not minimo <= int(valor) <= maximo:
                    raise ValueError(f"«{clave}» debe ser un número entre {minimo} y {maximo}.")
                self.ajustes[clave] = int(valor)
            self.ajustes.update(modelo=self.modelo.get().strip(),
                                operador=self.operador_config.get().strip(),
                                modo_simulacion=self.simulacion.get())
            self.bd.db.configuracion.replace_one({"_id": "app"}, self.ajustes, upsert=True)
            self.refrescar()
            self.aviso("Configuración guardada.")
        self.intentar(accion)


if __name__ == "__main__":
    LogiSmartApp().mainloop()
