import customtkinter as ctk
from tkinterdnd2 import DND_FILES, TkinterDnD
from pdf_manager import extraer_texto
from claude_client import procesar_pdf_completo
from database_manager import inicializar_bbdd, guardar_documento, insertar_poliza_completa
import threading

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

ICONOS_TIPO = {
    "AUTO":  "🚗",
    "HOGAR": "🏠",
    "VIDA":  "❤️",
    "SALUD": "🏥",
    "OTRO":  "📄",
}


class AppDemo(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self):
        super().__init__()
        self.TkDnDVersion = TkinterDnD._require(self)

        self.title("Claude PDF Extractor — Seguros")
        self.geometry("750x580")

        inicializar_bbdd()

        # ── Zona de arrastre ──────────────────────────────────────────────
        self.drop_label = ctk.CTkLabel(
            self, text="📂  Arrastra tu PDF de póliza aquí",
            width=680, height=120,
            fg_color="#2b2b2b", corner_radius=12,
            font=("Arial", 16, "bold")
        )
        self.drop_label.pack(pady=(20, 8), padx=20)
        self.drop_label.drop_target_register(DND_FILES)
        self.drop_label.dnd_bind('<<Drop>>', self.al_soltar_archivo)

        # ── Badge de tipo detectado ───────────────────────────────────────
        self.badge_tipo = ctk.CTkLabel(
            self, text="",
            fg_color="transparent",
            font=("Arial", 13)
        )
        self.badge_tipo.pack()

        # ── Botón procesar ────────────────────────────────────────────────
        self.btn_procesar = ctk.CTkButton(
            self, text="⚡  Analizar e insertar en BD",
            state="disabled", command=self.procesar,
            width=280, height=40
        )
        self.btn_procesar.pack(pady=8)

        # ── Barra de progreso ─────────────────────────────────────────────
        self.progress = ctk.CTkProgressBar(self, width=680, mode="indeterminate")
        self.progress.pack(pady=(0, 8), padx=20)
        self.progress.set(0)

        # ── Log de resultados ─────────────────────────────────────────────
        self.resultado_txt = ctk.CTkTextbox(self, width=700, height=320, font=("Courier", 12))
        self.resultado_txt.pack(pady=8, padx=20)

        self.archivo_actual = None

    # ─────────────────────────────────────────────────────────────────────
    # DRAG & DROP
    # ─────────────────────────────────────────────────────────────────────

    def al_soltar_archivo(self, event):
        ruta = event.data.strip("{}")
        if ruta.lower().endswith(".pdf"):
            self.archivo_actual = ruta
            nombre = ruta.split("/")[-1].split("\\")[-1]
            self.drop_label.configure(
                text=f"✓  {nombre}",
                fg_color="#1f538d"
            )
            self.badge_tipo.configure(text="")
            self.btn_procesar.configure(state="normal")
            self._log_clear()
            self._log(f"Archivo seleccionado: {nombre}\n")
        else:
            self.drop_label.configure(text="⚠️  Solo archivos PDF", fg_color="#8d1f1f")

    # ─────────────────────────────────────────────────────────────────────
    # PROCESADO
    # ─────────────────────────────────────────────────────────────────────

    def procesar(self):
        self.btn_procesar.configure(state="disabled")
        self.progress.start()
        hilo = threading.Thread(target=self._logica_pesada, daemon=True)
        hilo.start()

    def _logica_pesada(self):
        try:
            nombre = self.archivo_actual.split("/")[-1].split("\\")[-1]

            # 1. Extraer texto del PDF
            self._log("① Extrayendo texto del PDF...")
            texto = extraer_texto(self.archivo_actual)
            self._log(f"   {len(texto):,} caracteres extraídos\n")

            # 2. Claude detecta tipo y extrae campos
            self._log("② Enviando a Claude para detección y extracción...")
            tipo, datos = procesar_pdf_completo(texto)

            icono = ICONOS_TIPO.get(tipo, "📄")
            self._log(f"   Tipo detectado: {icono} {tipo}\n")
            self.badge_tipo.configure(text=f"{icono}  Póliza de {tipo.capitalize()} detectada")

            if "error" in datos:
                self._log(f"⚠️  Claude no pudo extraer datos: {datos['error']}\n")
                return

            # 3. Guardar documento maestro en BD
            self._log("③ Guardando documento en MySQL...")
            doc_id = guardar_documento(nombre, texto, tipo, datos)
            self._log(f"   Documento guardado (ID doc: {doc_id})\n")

            # 4. Insertar en tablas específicas
            self._log("④ Insertando en tablas de póliza...")
            id_pol = insertar_poliza_completa(doc_id, tipo, datos)
            self._log(f"   Póliza insertada (ID póliza: {id_pol})\n")

            # 5. Resumen de lo insertado
            self._log("─" * 55)
            self._log("RESUMEN DE CAMPOS EXTRAÍDOS:\n")
            self._mostrar_resumen(tipo, datos)
            self._log("─" * 55)
            self._log("✅  Proceso completado sin errores.")

        except Exception as e:
            self._log(f"\n❌  ERROR: {str(e)}")
        finally:
            self.progress.stop()
            self.progress.set(0)
            self.btn_procesar.configure(state="normal")

    # ─────────────────────────────────────────────────────────────────────
    # HELPERS DE LOG
    # ─────────────────────────────────────────────────────────────────────

    def _log(self, texto: str):
        self.resultado_txt.insert("end", texto + "\n")
        self.resultado_txt.see("end")

    def _log_clear(self):
        self.resultado_txt.delete("1.0", "end")

    def _mostrar_resumen(self, tipo: str, datos: dict):
        """Imprime los campos encontrados de forma legible."""

        def campo(seccion, clave, etiqueta):
            val = (datos.get(seccion) or {}).get(clave)
            if val is not None:
                self._log(f"  {etiqueta}: {val}")

        # Póliza
        campo("poliza", "numero_poliza", "Nº Póliza")
        campo("poliza", "efecto",        "Efecto")
        campo("poliza", "vencimiento",   "Vencimiento")
        campo("poliza", "forma_pago",    "Forma de pago")

        # Tomador
        tom = datos.get("tomador") or {}
        nombre_tom = f"{tom.get('nombre','')} {tom.get('apellidos','')}".strip()
        if nombre_tom:
            self._log(f"  Tomador: {nombre_tom}")
        campo("tomador", "nif", "  NIF")

        # Recibo
        campo("recibo", "total", "Total recibo")

        # Específico por tipo
        if tipo == "AUTO":
            v = datos.get("vehiculo") or {}
            if v.get("marca"):
                self._log(f"  Vehículo: {v.get('marca')} {v.get('modelo','')} ({v.get('matricula','')})")
            ncond = len([c for c in (datos.get("conductores") or []) if c and c.get("nif")])
            if ncond:
                self._log(f"  Conductores: {ncond}")
            ngar = len([g for g in (datos.get("garantias") or []) if g and g.get("nombre")])
            if ngar:
                self._log(f"  Garantías: {ngar}")

        elif tipo == "HOGAR":
            i = datos.get("inmueble") or {}
            if i.get("direccion"):
                self._log(f"  Inmueble: {i.get('direccion')}")

        elif tipo == "VIDA":
            a = datos.get("asegurado") or {}
            nombre_a = f"{a.get('nombre','')} {a.get('apellidos','')}".strip()
            if nombre_a:
                self._log(f"  Asegurado: {nombre_a}")
            nb = len([b for b in (datos.get("beneficiarios") or []) if b and b.get("nombre")])
            if nb:
                self._log(f"  Beneficiarios: {nb}")

        elif tipo == "SALUD":
            nas = len([a for a in (datos.get("asegurados") or []) if a and a.get("nif")])
            if nas:
                self._log(f"  Asegurados: {nas}")


if __name__ == "__main__":
    app = AppDemo()
    app.mainloop()