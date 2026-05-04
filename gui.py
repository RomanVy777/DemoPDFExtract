import customtkinter as ctk
from tkinterdnd2 import DND_FILES, TkinterDnD
from pdf_manager import extraer_texto
from claude_client import procesar_pdf_completo
from database_manager import inicializar_bbdd, guardar_documento, crear_tablas_desde_json_claude
import threading
import json

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

ICONOS_TIPO = {
    "AUTO": "AUTO",
    "HOGAR": "HOGAR",
    "VIDA": "VIDA",
    "SALUD": "SALUD",
    "DECESOS": "DECESOS",
    "COMERCIO": "COMERCIO",
    "COMUNIDAD": "COMUNIDAD",
    "OTRO": "OTRO",
}


class AppDemo(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self):
        super().__init__()
        self.TkDnDVersion = TkinterDnD._require(self)

        self.title("Claude PDF Extractor - Seguros")
        self.geometry("780x600")

        inicializar_bbdd()

        self.drop_label = ctk.CTkLabel(
            self,
            text="Arrastra tu PDF de póliza aquí",
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
            font=("Arial", 13)
        )
        self.badge_tipo.pack()

        self.btn_procesar = ctk.CTkButton(
            self,
            text="Analizar PDF e insertar en MySQL",
            state="disabled",
            command=self.procesar,
            width=300,
            height=40
        )
        self.btn_procesar.pack(pady=8)

        self.progress = ctk.CTkProgressBar(
            self,
            width=700,
            mode="indeterminate"
        )
        self.progress.pack(pady=(0, 8), padx=20)
        self.progress.set(0)

        self.resultado_txt = ctk.CTkTextbox(
            self,
            width=720,
            height=340,
            font=("Courier", 12)
        )
        self.resultado_txt.pack(pady=8, padx=20)

        self.archivo_actual = None

    def _asegurar_formato_dinamico(self, tipo, datos):
        """
        Convierte cualquier respuesta de Claude al formato dinámico:
        {
            "tipo_seguro": "...",
            "descripcion": "...",
            "tablas": {...}
        }
        """

        if not isinstance(datos, dict):
            return {
                "tipo_seguro": tipo or "OTRO",
                "descripcion": "Respuesta no válida",
                "tablas": {}
            }

        if "tablas" in datos and isinstance(datos["tablas"], dict):
            if "tipo_seguro" not in datos:
                datos["tipo_seguro"] = tipo or "OTRO"

            return datos

        tablas = {}

        claves_que_no_son_tablas = {
            "tipo_seguro",
            "tipo_poliza",
            "descripcion",
            "error"
        }

        for clave, valor in datos.items():
            if clave not in claves_que_no_son_tablas:
                tablas[clave] = valor

        return {
            "tipo_seguro": tipo or datos.get("tipo_seguro") or datos.get("tipo_poliza") or "OTRO",
            "descripcion": datos.get("descripcion", "Documento procesado por Claude"),
            "tablas": tablas
        }

    def al_soltar_archivo(self, event):
        ruta = event.data.strip("{}")

        if ruta.lower().endswith(".pdf"):
            self.archivo_actual = ruta

            nombre = ruta.split("/")[-1].split("\\")[-1]

            self.drop_label.configure(
                text=f"Archivo seleccionado: {nombre}",
                fg_color="#1f538d"
            )

            self.badge_tipo.configure(text="")
            self.btn_procesar.configure(state="normal")

            self._log_clear()
            self._log(f"Archivo seleccionado: {nombre}\n")

        else:
            self.drop_label.configure(
                text="Solo se permiten archivos PDF",
                fg_color="#8d1f1f"
            )

    def procesar(self):
        if not self.archivo_actual:
            self._log("No hay ningún archivo seleccionado.")
            return

        self.btn_procesar.configure(state="disabled")
        self.progress.start()

        hilo = threading.Thread(target=self._logica_pesada, daemon=True)
        hilo.start()

    def _logica_pesada(self):
        try:
            nombre = self.archivo_actual.split("/")[-1].split("\\")[-1]

            self._log_seguro("1. Extrayendo texto del PDF...")
            texto = extraer_texto(self.archivo_actual)

            if not texto or texto.strip() == "":
                self._log_seguro("No se ha podido extraer texto del PDF.")
                self._log_seguro("Puede que el PDF sea escaneado o una imagen.")
                return

            self._log_seguro(f"Texto extraído: {len(texto):,} caracteres\n")

            self._log_seguro("2. Enviando texto a Claude...")
            respuesta_claude = procesar_pdf_completo(texto)

            tipo, datos = self._normalizar_respuesta_claude(respuesta_claude)
            datos = self._asegurar_formato_dinamico(tipo, datos)

            if not datos:
                self._log_seguro("Claude no ha devuelto datos válidos.")
                return

            if "error" in datos:
                self._log_seguro(f"Claude devolvió un error: {datos['error']}")
                return

            tipo = tipo.upper() if tipo else "OTRO"

            self._log_seguro(f"Tipo de seguro detectado: {tipo}\n")
            self._configurar_badge(tipo)

            if "tablas" not in datos:
                self._log_seguro("El JSON de Claude no contiene la clave 'tablas'.")
                self._log_seguro("Revisa el prompt de claude_client.py.")
                self._log_seguro("\nJSON recibido:")
                self._log_seguro(json.dumps(datos, ensure_ascii=False, indent=4))
                return

            self._log_seguro("3. Guardando documento principal en MySQL...")

            id_documento = guardar_documento(
                nombre_archivo=nombre,
                tipo_seguro=tipo,
                texto_extraido=texto,
                datos_claude=datos
            )

            self._log_seguro(f"Documento guardado con ID: {id_documento}\n")

            self._log_seguro("4. Creando tablas dinámicas en MySQL...")
            crear_tablas_desde_json_claude(
                id_documento=id_documento,
                datos_claude=datos
            )

            tablas = datos.get("tablas", {})

            self._log_seguro("Tablas creadas o actualizadas:")

            for nombre_tabla in tablas.keys():
                self._log_seguro(f" - {nombre_tabla}")

            self._log_seguro("\n" + "-" * 60)
            self._log_seguro("RESUMEN DEL JSON DETECTADO")
            self._log_seguro("-" * 60)

            self._mostrar_resumen_dinamico(datos)

            self._log_seguro("-" * 60)
            self._log_seguro("Proceso completado correctamente.")

        except Exception as e:
            self._log_seguro(f"\nERROR: {str(e)}")

        finally:
            self.after(0, self._finalizar_proceso)

    def _normalizar_respuesta_claude(self, respuesta):
        """
        Permite trabajar con dos formatos distintos:

        Formato nuevo:
        {
            "tipo_seguro": "auto",
            "tablas": {...}
        }

        Formato antiguo:
        tipo, datos
        """
        if isinstance(respuesta, tuple):
            tipo, datos = respuesta

            if isinstance(datos, dict):
                if "tipo_seguro" not in datos:
                    datos["tipo_seguro"] = tipo

                return tipo, datos

        if isinstance(respuesta, dict):
            tipo = respuesta.get("tipo_seguro", "OTRO")
            return tipo, respuesta

        return "OTRO", {}

    def _mostrar_resumen_dinamico(self, datos):
        tipo = datos.get("tipo_seguro", "OTRO")
        descripcion = datos.get("descripcion", "")

        self._log_seguro(f"Tipo de seguro: {tipo}")

        if descripcion:
            self._log_seguro(f"Descripción: {descripcion}")

        tablas = datos.get("tablas", {})

        if not tablas:
            self._log_seguro("No se detectaron tablas.")
            return

        self._log_seguro(f"Número de tablas detectadas: {len(tablas)}\n")

        for nombre_tabla, contenido in tablas.items():
            self._log_seguro(f"Tabla: {nombre_tabla}")

            if isinstance(contenido, dict):
                self._log_seguro(f"  Registros: 1")
                self._log_seguro(f"  Campos: {len(contenido.keys())}")

                for clave, valor in list(contenido.items())[:6]:
                    self._log_seguro(f"    {clave}: {valor}")

            elif isinstance(contenido, list):
                self._log_seguro(f"  Registros: {len(contenido)}")

                if len(contenido) > 0 and isinstance(contenido[0], dict):
                    self._log_seguro(f"  Campos por registro: {len(contenido[0].keys())}")

                    for clave, valor in list(contenido[0].items())[:6]:
                        self._log_seguro(f"    {clave}: {valor}")

            else:
                self._log_seguro(f"  Valor: {contenido}")

            self._log_seguro("")

    def _configurar_badge(self, tipo):
        texto = f"Póliza de {tipo} detectada"
        self.after(0, lambda: self.badge_tipo.configure(text=texto))

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