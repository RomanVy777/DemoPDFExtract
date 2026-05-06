import os
import re
import json
import threading
import customtkinter as ctk
from tkinterdnd2 import DND_FILES, TkinterDnD
from pdf_manager import extraer_texto
# Asegúrate de que estas funciones existan en tu claude_client.py y database_manager.py
from claude_client import procesar_pdf_completo
from database_manager import inicializar_bbdd, guardar_documento, crear_tablas_desde_json_claude

# Configuramos el estilo visual
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class AppDemo(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self):
        super().__init__()
        self.TkDnDVersion = TkinterDnD._require(self)

        self.title("Claude PDF Extractor - Seguros (Oracle Edition)")
        self.geometry("780x650")

        # Inicializar estructura base en Oracle
        try:
            inicializar_bbdd()
        except Exception as e:
            print(f"Error al conectar con Oracle: {e}")

        # --- UI: Área de Arrastre ---
        self.drop_label = ctk.CTkLabel(
            self,
            text="Arrastra tu póliza PDF aquí para procesar en Oracle",
            width=700,
            height=120,
            fg_color="#2b2b2b",
            corner_radius=12,
            font=("Arial", 16, "bold")
        )
        self.drop_label.pack(pady=(20, 8), padx=20)

        self.drop_label.drop_target_register(DND_FILES)
        self.drop_label.dnd_bind("<<Drop>>", self.al_soltar_archivo)

        self.badge_tipo = ctk.CTkLabel(
            self,
            text="",
            fg_color="transparent",
            font=("Arial", 13, "italic")
        )
        self.badge_tipo.pack()

        # --- UI: Botón ---
        self.btn_procesar = ctk.CTkButton(
            self,
            text="Analizar PDF e insertar en Oracle",
            state="disabled",
            command=self.procesar,
            width=300,
            height=40
        )
        self.btn_procesar.pack(pady=8)

        # --- UI: Progreso ---
        self.progress = ctk.CTkProgressBar(
            self,
            width=700,
            mode="indeterminate"
        )
        self.progress.pack(pady=(0, 8), padx=20)
        self.progress.set(0)

        # --- UI: Consola de Resultados ---
        self.resultado_txt = ctk.CTkTextbox(
            self,
            width=720,
            height=340,
            font=("Courier", 12)
        )
        self.resultado_txt.pack(pady=8, padx=20)

        self.archivo_actual = None

    def al_soltar_archivo(self, event):
        # Limpiar llaves que a veces añade Windows en rutas con espacios
        ruta = event.data.strip("{}")

        if ruta.lower().endswith(".pdf"):
            self.archivo_actual = ruta
            nombre = os.path.basename(ruta)

            self.drop_label.configure(
                text=f"Archivo seleccionado: {nombre}",
                fg_color="#1f538d"
            )

            self.badge_tipo.configure(text="")
            self.btn_procesar.configure(state="normal")

            self._log_clear()
            self._log(f"Archivo listo: {nombre}\n")
        else:
            self.drop_label.configure(
                text="Error: Solo se admiten archivos PDF",
                fg_color="#8d1f1f"
            )

    def procesar(self):
        if not self.archivo_actual:
            return

        self.btn_procesar.configure(state="disabled")
        self.progress.start()

        # Ejecución en segundo plano para no congelar la ventana
        hilo = threading.Thread(target=self._logica_pesada, daemon=True)
        hilo.start()

    def _logica_pesada(self):
        try:
            nombre = os.path.basename(self.archivo_actual)

            self._log_seguro("1. Leyendo contenido del PDF...")
            texto = extraer_texto(self.archivo_actual)

            if not texto or len(texto.strip()) < 10:
                self._log_seguro("! Error: El PDF no contiene texto legible (¿Es una imagen?)")
                return

            self._log_seguro(f"✓ Texto extraído ({len(texto)} caracteres)")

            self._log_seguro("2. Consultando a Claude AI...")
            respuesta_claude = procesar_pdf_completo(texto)

            # Normalizar la respuesta para asegurar que tenemos la estructura de tablas
            tipo, datos = self._normalizar_respuesta_claude(respuesta_claude)
            datos = self._asegurar_formato_dinamico(tipo, datos)

            self._log_seguro(f"✓ Claude identificó seguro de tipo: {tipo.upper()}")
            self._configurar_badge(tipo.upper())

            # 3. Guardar Documento Principal en Oracle
            self._log_seguro("3. Registrando documento en tabla maestra de Oracle...")
            id_documento = guardar_documento(
                nombre_archivo=nombre,
                tipo_seguro=tipo,
                texto_extraido=texto,
                datos_claude=datos
            )
            self._log_seguro(f"✓ Guardado con éxito. Oracle ID: {id_documento}")

            # 4. Crear tablas dinámicas basadas en el JSON
            self._log_seguro("4. Generando tablas y columnas dinámicas...")
            crear_tablas_desde_json_claude(
                id_documento=id_documento,
                datos_claude=datos
            )

            # Resumen final en la consola
            self._log_seguro("\n" + "="*40)
            self._log_seguro("PROCESO FINALIZADO EN ORACLE")
            self._log_seguro("="*40)
            self._mostrar_resumen_dinamico(datos)

        except Exception as e:
            self._log_seguro(f"\n❌ ERROR CRÍTICO: {str(e)}")
        finally:
            self.after(0, self._finalizar_proceso)

    def _normalizar_respuesta_claude(self, respuesta):
        """ Maneja si la respuesta viene como tupla (tipo, dict) o solo dict """
        if isinstance(respuesta, tuple):
            return respuesta
        if isinstance(respuesta, dict):
            return respuesta.get("tipo_seguro", "OTRO"), respuesta
        return "OTRO", {}

    def _asegurar_formato_dinamico(self, tipo, datos):
        """ Garantiza que el diccionario tenga la estructura de 'tablas' """
        if not isinstance(datos, dict):
            return {"tipo_seguro": tipo, "tablas": {}}

        if "tablas" in datos:
            return datos

        # Si Claude devolvió campos sueltos, los agrupamos en una tabla por defecto
        tablas_limpias = {}
        excluir = {"tipo_seguro", "descripcion", "error"}

        datos_tabla = {k: v for k, v in datos.items() if k not in excluir}
        return {
            "tipo_seguro": tipo,
            "descripcion": datos.get("descripcion", "Procesado dinámicamente"),
            "tablas": {"DATOS_GENERALES": datos_tabla}
        }

    def _mostrar_resumen_dinamico(self, datos):
        tablas = datos.get("tablas", {})
        for nombre_tabla, contenido in tablas.items():
            count = len(contenido) if isinstance(contenido, list) else 1
            self._log_seguro(f"📋 Tabla Oracle: {nombre_tabla.upper()} ({count} registros)")

    def _configurar_badge(self, tipo):
        self.after(0, lambda: self.badge_tipo.configure(text=f"⦿ TIPO: {tipo}", text_color="#52d378"))

    def _finalizar_proceso(self):
        self.progress.stop()
        self.progress.set(0)
        self.btn_procesar.configure(state="normal")

    def _log_seguro(self, texto):
        self.after(0, lambda: self._log(texto))

    def _log(self, texto):
        self.resultado_txt.insert("end", texto + "\n")
        self.resultado_txt.see("end")

    def _log_clear(self):
        self.resultado_txt.delete("1.0", "end")

if __name__ == "__main__":
    app = AppDemo()
    app.mainloop()