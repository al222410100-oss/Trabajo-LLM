# ============================================================
# PARTE 1 - INTERFAZ GRÁFICA DEL ASISTENTE DE BOXEO (tkinter)
# Ejecutar:  python LLM/tutor_gui.py
# ============================================================

import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from tutor_llm import TutorLLM, MODELO_POR_DEFECTO

SUGERENCIAS = [
    "¿Cómo mejoro mi jab?",
    "Dame una rutina de saco de 6 asaltos para principiante",
    "¿Cómo bajo de peso sin perder fuerza antes de una pelea?",
]


FONDO = "#14161b"
PANEL = "#1d2027"
PANEL_ALT = "#272b34"
BORDE = "#333843"
ROJO = "#e63946"
ROJO_HOVER = "#f25864"
DORADO = "#f4b942"
TEXTO = "#e9eaec"
TENUE = "#9097a3"
ERROR = "#ff7b72"

FUENTE = ("Segoe UI", 11)
FUENTE_NEGRITA = ("Segoe UI", 10, "bold")
FUENTE_PEQUE = ("Segoe UI", 9)
FUENTE_TITULO = ("Segoe UI", 17, "bold")


class TutorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Asistente de Entrenamiento para Boxeadores")
        self.geometry("960x700")
        self.minsize(760, 520)
        self.configure(bg=FONDO)

        self.tutor = TutorLLM()
        self.cola = queue.Queue()      # resultados de hilos -> GUI
        self.ocupado = False

        self._crear_estilos()
        self._crear_widgets()
        self._agregar("Entrenador", "¡Hola, campeón! Soy tu entrenador "
                      "asistente de boxeo. ¿Qué quieres trabajar hoy?")
        self.after(100, self._revisar_cola)

    # --------------------------------------------------------
    # Estilos
    # --------------------------------------------------------
    def _crear_estilos(self):
        estilo = ttk.Style(self)
        estilo.theme_use("clam")
        estilo.configure(
            "TCombobox", fieldbackground=PANEL_ALT, background=PANEL_ALT,
            foreground=TEXTO, arrowcolor=TEXTO, bordercolor=BORDE,
            lightcolor=PANEL_ALT, darkcolor=PANEL_ALT, padding=4)
        estilo.map("TCombobox",
                   fieldbackground=[("readonly", PANEL_ALT)],
                   foreground=[("readonly", TEXTO)])
        estilo.configure(
            "Vertical.TScrollbar", background=PANEL_ALT, troughcolor=PANEL,
            bordercolor=PANEL, lightcolor=PANEL_ALT, darkcolor=PANEL_ALT,
            arrowcolor=TENUE)
        estilo.map("Vertical.TScrollbar",
                   background=[("disabled", PANEL), ("active", BORDE)],
                   arrowcolor=[("disabled", PANEL)])
        estilo.configure(
            "Horizontal.TProgressbar", background=ROJO, troughcolor=PANEL_ALT,
            bordercolor=FONDO, lightcolor=ROJO, darkcolor=ROJO)
        
        self.option_add("*TCombobox*Listbox.background", PANEL_ALT)
        self.option_add("*TCombobox*Listbox.foreground", TEXTO)
        self.option_add("*TCombobox*Listbox.selectBackground", ROJO)
        self.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")

    def _boton(self, padre, texto, comando, primario=False, fuente=FUENTE_PEQUE):
        """Botón plano con efecto al pasar el ratón."""
        normal, encima = (ROJO, ROJO_HOVER) if primario else (PANEL_ALT, BORDE)
        b = tk.Button(
            padre, text=texto, command=comando, font=fuente,
            bg=normal, fg="#ffffff" if primario else TEXTO,
            activebackground=encima, activeforeground="#ffffff",
            disabledforeground=TENUE, relief="flat", bd=0,
            padx=12, pady=6, cursor="hand2")
        b.bind("<Enter>", lambda e: str(b["state"]) == "normal"
               and b.configure(bg=encima))
        b.bind("<Leave>", lambda e: b.configure(bg=normal))
        return b

    # --------------------------------------------------------
    # Construcción de la interfaz
    # --------------------------------------------------------
    def _crear_widgets(self):
        # Encabezado
        cab = tk.Frame(self, bg=PANEL)
        cab.pack(fill="x")
        tk.Frame(cab, bg=ROJO, height=4).pack(fill="x")
        interior = tk.Frame(cab, bg=PANEL, padx=18, pady=12)
        interior.pack(fill="x")

        titulos = tk.Frame(interior, bg=PANEL)
        titulos.pack(side="left")
        tk.Label(titulos, text="🥊  ESQUINA ROJA", font=FUENTE_TITULO,
                 bg=PANEL, fg=TEXTO).pack(anchor="w")
        tk.Label(titulos, text="Tu entrenador asistente de boxeo",
                 font=FUENTE_PEQUE, bg=PANEL, fg=TENUE).pack(anchor="w")

        acciones = tk.Frame(interior, bg=PANEL)
        acciones.pack(side="right")
        self._boton(acciones, "Resumen del historial",
                    self._mostrar_resumen, primario=True).pack(
                        side="right", padx=(6, 0))
        self._boton(acciones, "Guardar chat",
                    self._guardar).pack(side="right", padx=(6, 0))
        self._boton(acciones, "Nueva conversación",
                    self._nueva).pack(side="right", padx=(6, 0))

        modelos = self.tutor.modelos_disponibles() or [MODELO_POR_DEFECTO]
        inicial = next((m for m in modelos
                        if m.startswith(MODELO_POR_DEFECTO)), modelos[0])
        self.var_modelo = tk.StringVar(value=inicial)
        ttk.Combobox(acciones, textvariable=self.var_modelo, values=modelos,
                     width=20, font=FUENTE_PEQUE).pack(side="right",
                                                       padx=(6, 10))
        tk.Label(acciones, text="Modelo", font=FUENTE_PEQUE,
                 bg=PANEL, fg=TENUE).pack(side="right")

        # Pie: estado + spinner (se empaqueta antes para quedar abajo)
        estado = tk.Frame(self, bg=FONDO, padx=18, pady=8)
        estado.pack(side="bottom", fill="x")
        self.var_estado = tk.StringVar(value="Listo")
        tk.Label(estado, textvariable=self.var_estado, font=FUENTE_PEQUE,
                 bg=FONDO, fg=TENUE).pack(side="left")
        self.spinner = ttk.Progressbar(estado, mode="indeterminate",
                                       length=160)

        # Entrada
        entrada = tk.Frame(self, bg=FONDO, padx=18)
        entrada.pack(side="bottom", fill="x")
        caja = tk.Frame(entrada, bg=PANEL_ALT, highlightthickness=1,
                        highlightbackground=BORDE, highlightcolor=ROJO)
        caja.pack(side="left", fill="x", expand=True)
        self.var_entrada = tk.StringVar()
        self.entry = tk.Entry(caja, textvariable=self.var_entrada, font=FUENTE,
                              bg=PANEL_ALT, fg=TEXTO, insertbackground=TEXTO,
                              relief="flat", bd=0)
        self.entry.pack(fill="x", padx=12, pady=10)
        self.entry.bind("<Return>", lambda e: self._enviar())
        self.entry.focus()
        self.btn = self._boton(entrada, "Enviar  ➤", self._enviar,
                               primario=True, fuente=FUENTE_NEGRITA)
        self.btn.pack(side="left", padx=(8, 0), fill="y")

        # Sugerencias
        sug = tk.Frame(self, bg=FONDO, padx=18, pady=10)
        sug.pack(side="bottom", fill="x")
        tk.Label(sug, text="Prueba:", font=FUENTE_PEQUE,
                 bg=FONDO, fg=TENUE).pack(side="left", padx=(0, 6))
        for s in SUGERENCIAS:
            self._boton(sug, s if len(s) < 38 else s[:35] + "...",
                        lambda t=s: self._enviar(t)).pack(side="left", padx=3)

        # Zona de conversación
        marco = tk.Frame(self, bg=PANEL, highlightthickness=1,
                         highlightbackground=BORDE)
        marco.pack(fill="both", expand=True, padx=18, pady=(14, 0))
        self.txt = tk.Text(
            marco, wrap="word", state="disabled", font=FUENTE,
            bg=PANEL, fg=TEXTO, relief="flat", bd=0, padx=18, pady=14,
            spacing2=3, selectbackground=ROJO, selectforeground="#ffffff",
            cursor="arrow")
        scroll = ttk.Scrollbar(marco, command=self.txt.yview)
        self.txt.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.txt.pack(fill="both", expand=True)

        # Nombre del emisor (una etiqueta por tipo) y cuerpo del mensaje
        for tag, color in (("usuario", ROJO), ("entrenador", DORADO),
                           ("sistema", TENUE), ("error", ERROR)):
            self.txt.tag_configure(tag, foreground=color,
                                   font=FUENTE_NEGRITA, spacing1=10,
                                   spacing3=3)
        self.txt.tag_configure("cuerpo", lmargin1=14, lmargin2=14,
                               rmargin=30, spacing3=8)
        self.txt.tag_configure("cuerpo_sistema", lmargin1=14, lmargin2=14,
                               rmargin=30, spacing3=8, foreground=TENUE,
                               font=("Segoe UI", 10, "italic"))
        self.txt.tag_configure("cuerpo_error", lmargin1=14, lmargin2=14,
                               rmargin=30, spacing3=8, foreground=ERROR)

    # --------------------------------------------------------
    # Utilidades de la zona de texto
    # --------------------------------------------------------
    def _agregar(self, quien, texto, etiqueta=None):
        tag = etiqueta or quien.lower()
        cuerpo = {"sistema": "cuerpo_sistema",
                  "error": "cuerpo_error"}.get(tag, "cuerpo")
        self.txt.configure(state="normal")
        self.txt.insert("end", f"{quien.upper()}\n", tag)
        self.txt.insert("end", f"{texto.strip()}\n", cuerpo)
        self.txt.configure(state="disabled")
        self.txt.see("end")

    def _ocupar(self, mensaje):
        self.ocupado = True
        self.btn.configure(state="disabled", bg=PANEL_ALT)
        self.var_estado.set(mensaje)
        self.spinner.pack(side="right")
        self.spinner.start(12)

    def _liberar(self):
        self.ocupado = False
        self.btn.configure(state="normal", bg=ROJO)
        self.var_estado.set("Listo")
        self.spinner.stop()
        self.spinner.pack_forget()
        self.entry.focus()

    # --------------------------------------------------------
    # Acciones
    # --------------------------------------------------------
    def _usar_modelo(self):
        self.tutor.modelo = self.var_modelo.get().strip() or MODELO_POR_DEFECTO

    def _enviar(self, texto=None):
        if self.ocupado:
            return
        texto = (texto or self.var_entrada.get()).strip()
        if not texto:
            self.var_estado.set("Escribe una pregunta antes de enviar.")
            return
        if len(texto) > 2000:
            messagebox.showwarning("Texto muy largo",
                                   "Limita la pregunta a 2000 caracteres.")
            return
        self._usar_modelo()
        self.var_entrada.set("")
        self._agregar("Tú", texto, "usuario")
        self._ocupar("El entrenador está pensando...")
        self._en_hilo("respuesta", lambda: self.tutor.preguntar(texto))

    def _mostrar_resumen(self):
        if self.ocupado:
            return
        if not self.tutor.turnos():
            messagebox.showinfo("Resumen", "Aún no hay conversación.")
            return
        self._usar_modelo()
        self._ocupar("Generando resumen...")
        self._en_hilo("resumen", self.tutor.resumen)

    def _nueva(self):
        if self.ocupado:
            return
        if self.tutor.turnos() and not messagebox.askyesno(
                "Nueva conversación", "Se borrará el historial. ¿Continuar?"):
            return
        self.tutor.reiniciar()
        self.txt.configure(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.configure(state="disabled")
        self._agregar("Entrenador", "Conversación reiniciada. ¿Qué trabajamos?")

    def _guardar(self):
        turnos = self.tutor.turnos()
        if not turnos:
            messagebox.showinfo("Guardar", "No hay nada que guardar.")
            return
        ruta = filedialog.asksaveasfilename(
            defaultextension=".txt", filetypes=[("Texto", "*.txt")])
        if not ruta:
            return
        with open(ruta, "w", encoding="utf-8") as f:
            for m in turnos:
                f.write(f"{'Boxeador' if m['role'] == 'user' else 'Entrenador'}: "
                        f"{m['content']}\n\n")
        self.var_estado.set(f"Guardado en {ruta}")

    # --------------------------------------------------------
    # Hilos: la llamada al LLM no debe congelar la ventana
    # --------------------------------------------------------
    def _en_hilo(self, tipo, funcion):
        def tarea():
            try:
                self.cola.put((tipo, funcion(), None))
            except Exception as e:
                self.cola.put((tipo, None, e))
        threading.Thread(target=tarea, daemon=True).start()

    def _revisar_cola(self):
        try:
            while True:
                tipo, dato, error = self.cola.get_nowait()
                self._liberar()
                if error:
                    self._agregar(
                        "Error",
                        "No se pudo contactar con el LLM.\n"
                        "Verifica que Ollama esté ejecutándose y que el "
                        f"modelo '{self.tutor.modelo}' esté instalado "
                        f"(ollama pull {self.tutor.modelo}).\n"
                        f"Detalle: {error}", "error")
                elif tipo == "respuesta":
                    self._agregar("Entrenador", dato)
                else:
                    self._agregar("Resumen de la conversación", dato,
                                  "sistema")
        except queue.Empty:
            pass
        self.after(100, self._revisar_cola)


def main():
    TutorApp().mainloop()


if __name__ == "__main__":
    main()
