# -*- coding: utf-8 -*-
"""
Interfaz gráfica local (Tkinter, sin dependencias externas) para ejecutar
ACTUALIZAR_Y_PUBLICAR.bat con un botón, en vez de doble clic en el .bat.

IMPORTANTE — esta interfaz NO contiene ninguna lógica de actualización,
validación ni Git. Es exclusivamente un lanzador: ejecuta el .bat ya existente
mediante subprocess y muestra su salida real en pantalla. Todo el "motor"
real del proceso sigue viviendo, sin cambios, en:
  - ACTUALIZADOR/actualizar_visor.py
  - ACTUALIZADOR/publicar_visor.py
  - ACTUALIZAR_Y_PUBLICAR.bat

Esta interfaz nunca llama directamente a los scripts .py: siempre invoca el
.bat, para mantener un único flujo oficial de actualización/publicación.

Uso: python actualizar_gui.py   (o doble clic en ABRIR_INTERFAZ.bat, en la
raíz del proyecto, que solo se encarga de encontrar Python y lanzar esto).
"""
import subprocess
import sys
import threading
import queue
import webbrowser
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import scrolledtext, messagebox

# La carpeta raíz del proyecto es SIEMPRE la carpeta que contiene a este
# archivo (APP_ACTUALIZACION/) subiendo un nivel -- esto funciona sin importar
# desde dónde se lance el script (doble clic, acceso directo, otra carpeta),
# porque __file__ apunta a la ubicación real de este archivo en disco, no al
# directorio de trabajo actual.
PROYECTO_DIR = Path(__file__).resolve().parent.parent
BAT_PATH = PROYECTO_DIR / "ACTUALIZAR_Y_PUBLICAR.bat"
URL_VISOR = "https://davidcarterc86-debug.github.io/visor-neumo23-2026-nuble/"

# Paleta reutilizada del propio visor (css/estilo.css), para que la interfaz
# se vea coherente con la identidad visual institucional ya aprobada.
COLOR_FONDO = "#eef4f7"
COLOR_AZUL = "#0b4f6c"
COLOR_AZUL_CLARO = "#1c7293"
COLOR_VERDE = "#2e7d5b"
COLOR_NARANJA = "#b5541a"
COLOR_GRIS = "#6b7280"
COLOR_BORDE = "#d9dfe4"


class AppActualizacion:
    def __init__(self, root):
        self.root = root
        self.root.title("Visor Neumo23 2026 - Ñuble | Actualización y publicación")
        self.root.geometry("780x580")
        self.root.minsize(640, 460)
        self.root.configure(bg=COLOR_FONDO)

        self.proceso = None
        self.ejecutando = False
        self.cola_salida = queue.Queue()

        self._construir_interfaz()
        self._verificar_bat()
        self.root.protocol("WM_DELETE_WINDOW", self._al_cerrar)

    # ------------------------------------------------------------
    # Construcción de la interfaz
    # ------------------------------------------------------------
    def _construir_interfaz(self):
        encabezado = tk.Frame(self.root, bg=COLOR_AZUL)
        encabezado.pack(fill="x")
        tk.Label(
            encabezado, text="Visor Neumo23 2026 — Ñuble", font=("Segoe UI", 16, "bold"),
            bg=COLOR_AZUL, fg="white", anchor="w", padx=16,
        ).pack(fill="x", pady=(10, 0))
        tk.Label(
            encabezado, text="Actualización y publicación", font=("Segoe UI", 10),
            bg=COLOR_AZUL, fg="#cfe3ec", anchor="w", padx=16,
        ).pack(fill="x", pady=(0, 10))

        cuerpo = tk.Frame(self.root, bg=COLOR_FONDO, padx=16, pady=14)
        cuerpo.pack(fill="both", expand=True)

        fila_botones = tk.Frame(cuerpo, bg=COLOR_FONDO)
        fila_botones.pack(fill="x", pady=(0, 10))

        self.btn_actualizar = tk.Button(
            fila_botones, text="ACTUALIZAR Y PUBLICAR", font=("Segoe UI", 12, "bold"),
            bg=COLOR_AZUL, fg="white", activebackground=COLOR_AZUL_CLARO, activeforeground="white",
            relief="flat", padx=18, pady=14, cursor="hand2", command=self._al_click_actualizar,
        )
        self.btn_actualizar.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.btn_abrir_visor = tk.Button(
            fila_botones, text="ABRIR VISOR", font=("Segoe UI", 11),
            bg="white", fg=COLOR_AZUL, activebackground="#f0f4f6",
            relief="solid", bd=1, padx=14, pady=14, cursor="hand2", command=self._abrir_visor,
        )
        self.btn_abrir_visor.pack(side="left")

        self.var_estado = tk.StringVar(value="Listo para actualizar.")
        self.lbl_estado = tk.Label(
            cuerpo, textvariable=self.var_estado, font=("Segoe UI", 11, "bold"),
            bg=COLOR_FONDO, fg=COLOR_GRIS, anchor="w",
        )
        self.lbl_estado.pack(fill="x", pady=(0, 8))

        tk.Label(
            cuerpo, text="Registro del proceso:", font=("Segoe UI", 9),
            bg=COLOR_FONDO, fg=COLOR_GRIS, anchor="w",
        ).pack(fill="x")
        self.txt_log = scrolledtext.ScrolledText(
            cuerpo, font=("Consolas", 9), bg="#0b1e26", fg="#d7e6ec",
            insertbackground="white", wrap="word", state="disabled", relief="flat", borderwidth=0,
        )
        self.txt_log.pack(fill="both", expand=True, pady=(4, 0))

        tk.Label(
            self.root, text="Herramienta local · Solo publica cuando presionas el botón",
            font=("Segoe UI", 8), bg=COLOR_FONDO, fg=COLOR_GRIS,
        ).pack(fill="x", pady=(0, 6))

    def _verificar_bat(self):
        self._log(f"Carpeta del proyecto detectada: {PROYECTO_DIR}")
        if not BAT_PATH.exists():
            self._log(f"[ERROR] No se encontró {BAT_PATH}")
            self._set_estado("No se encontró ACTUALIZAR_Y_PUBLICAR.bat", COLOR_NARANJA)
            self.btn_actualizar.config(state="disabled")
        else:
            self._log(f"Se ejecutará: {BAT_PATH}")

    # ------------------------------------------------------------
    # Utilidades de UI
    # ------------------------------------------------------------
    def _set_estado(self, texto, color=COLOR_GRIS):
        self.var_estado.set(texto)
        self.lbl_estado.config(fg=color)

    def _log(self, texto):
        self.txt_log.config(state="normal")
        self.txt_log.insert("end", texto + "\n")
        self.txt_log.see("end")
        self.txt_log.config(state="disabled")

    def _abrir_visor(self):
        webbrowser.open(URL_VISOR)

    # ------------------------------------------------------------
    # Ejecución del .bat (única vía permitida: subprocess sobre el .bat)
    # ------------------------------------------------------------
    def _al_click_actualizar(self):
        if self.ejecutando:
            return  # evita iniciar una segunda ejecución en paralelo
        if not BAT_PATH.exists():
            messagebox.showerror("Archivo no encontrado", f"No se encontró:\n{BAT_PATH}")
            return

        self.ejecutando = True
        self.btn_actualizar.config(state="disabled", text="EJECUTANDO...")
        self.txt_log.config(state="normal")
        self.txt_log.delete("1.0", "end")
        self.txt_log.config(state="disabled")
        self._set_estado("Preparando actualización...", COLOR_AZUL)
        self._log(f"=== Inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
        self._log(f"Ejecutando: {BAT_PATH}")
        self._log("")

        hilo = threading.Thread(target=self._ejecutar_bat, daemon=True)
        hilo.start()
        self.root.after(100, self._procesar_cola)

    def _ejecutar_bat(self):
        """Corre en un hilo aparte para no congelar la interfaz. Solo ejecuta
        el .bat -- nunca llama directamente a actualizar_visor.py ni a
        publicar_visor.py."""
        try:
            self.proceso = subprocess.Popen(
                ["cmd.exe", "/c", str(BAT_PATH)],
                cwd=str(PROYECTO_DIR),
                stdin=subprocess.DEVNULL,  # el .bat termina con "pause"; sin
                                           # una consola interactiva real,
                                           # continúa de inmediato en vez de
                                           # quedar colgado esperando una tecla.
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            for linea in self.proceso.stdout:
                self.cola_salida.put(("linea", linea.rstrip("\n")))
            codigo = self.proceso.wait()
            self.cola_salida.put(("fin", codigo))
        except Exception as e:
            self.cola_salida.put(("excepcion", str(e)))

    def _procesar_cola(self):
        """Vacía la cola de salida del hilo de trabajo hacia la interfaz.
        Tkinter no es seguro para actualizarse desde otro hilo, por eso el
        hilo de trabajo solo escribe en una queue.Queue() y este método,
        llamado periódicamente desde el hilo principal vía root.after(),
        es el único que toca los widgets."""
        try:
            while True:
                tipo, valor = self.cola_salida.get_nowait()
                if tipo == "linea":
                    self._log(valor)
                    self._actualizar_estado_por_linea(valor)
                elif tipo == "fin":
                    self._finalizar(valor)
                    return
                elif tipo == "excepcion":
                    self._log(f"[ERROR] No se pudo ejecutar el proceso: {valor}")
                    self._finalizar(-1)
                    return
        except queue.Empty:
            pass
        if self.ejecutando:
            self.root.after(100, self._procesar_cola)

    def _actualizar_estado_por_linea(self, linea):
        """El estado mostrado se DERIVA de marcadores que ya imprimen
        actualizar_visor.py / publicar_visor.py -- nunca se adelanta ni se
        inventa un resultado antes de que ocurra realmente."""
        if "PASO 1/6" in linea:
            self._set_estado("Actualizando datos...", COLOR_AZUL)
        elif "PASO 2/6" in linea:
            self._set_estado("Validando...", COLOR_AZUL)
        elif "PASO 3/6" in linea or "PASO 4/6" in linea:
            self._set_estado("Revisando cambios...", COLOR_AZUL)
        elif "PASO 5/6" in linea or "PASO 6/6" in linea or "Registrando publicación" in linea:
            self._set_estado("Publicando...", COLOR_AZUL)

    def _finalizar(self, codigo):
        self.ejecutando = False
        self.btn_actualizar.config(state="normal", text="ACTUALIZAR Y PUBLICAR")
        self._log("")
        self._log(f"=== Fin: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} "
                   f"(código de salida {codigo}) ===")
        if codigo == 0:
            self._set_estado("✓ Actualización y publicación completadas correctamente", COLOR_VERDE)
        else:
            self._set_estado("✗ El proceso terminó con errores", COLOR_NARANJA)
            messagebox.showwarning(
                "Proceso terminado con errores",
                "El proceso terminó con errores (código %d).\n"
                "Revisa el registro en la ventana principal para más detalles." % codigo,
            )

    def _al_cerrar(self):
        if self.ejecutando:
            if not messagebox.askyesno(
                "Proceso en ejecución",
                "Hay una actualización en curso. ¿Seguro que quieres cerrar la ventana?\n\n"
                "El proceso ya iniciado (actualizar_visor.py / git) seguirá corriendo en "
                "segundo plano hasta que termine por su cuenta.",
            ):
                return
        self.root.destroy()


def main():
    root = tk.Tk()
    AppActualizacion(root)
    root.mainloop()


if __name__ == "__main__":
    main()
