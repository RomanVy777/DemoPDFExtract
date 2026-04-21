import customtkinter as ctk
from tkinterdnd2 import DND_FILES, TkinterDnD
from pdf_manager import extraer_texto
from claude_client import llamar_a_claude
from database_manager import inicializar_bbdd, guardar_documento, actualizar_respuesta_claude
import threading

# Configuramos el estilo
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class AppDemo(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self):
        super().__init__()
        self.TkDnDVersion = TkinterDnD._require(self)

        self.title("Claude PDF Extractor - Empresa Demo")
        self.geometry("700x500")




        inicializar_bbdd()


        self.drop_label = ctk.CTkLabel(
            self, text="Arrastra tu PDF aquí",
            width=600, height=150,
            fg_color="#2b2b2b", corner_radius=10,
            font=("Arial", 16, "bold")
        )
        self.drop_label.pack(pady=20, padx=20)

        # Habilitar el Drag & Drop
        self.drop_label.drop_target_register(DND_FILES)
        self.drop_label.dnd_bind('<<Drop>>', self.al_soltar_archivo)

        # --- Botón de procesar ---
        self.btn_procesar = ctk.CTkButton(self, text="Analizar con Claude", state="disabled", command=self.procesar)
        self.btn_procesar.pack(pady=10)

        # --- Cuadro de texto para resultado ---
        self.resultado_txt = ctk.CTkTextbox(self, width=600, height=200)
        self.resultado_txt.pack(pady=20, padx=20)

        self.archivo_actual = None

    def al_soltar_archivo(self, event):
        ruta = event.data.strip("{}")
        if ruta.lower().endswith(".pdf"):
            self.archivo_actual = ruta
            self.drop_label.configure(text=f"Archivo cargado:\n{ruta.split('/')[-1]}", fg_color="#1f538d")
            self.btn_procesar.configure(state="normal")
        else:
            self.drop_label.configure(text="¡Error! Solo archivos PDF", fg_color="#8d1f1f")


    def procesar(self):
        self.btn_procesar.configure(state="disabled")
        self.resultado_txt.delete("1.0", "end")

        # Hilo para no congelar la GUI
        hilo = threading.Thread(target=self._logica_pesada)
        hilo.start()

    def _logica_pesada(self):
        try:
            nombre_fichero = self.archivo_actual.split('/')[-1]
            self.resultado_txt.insert("end", f"Extrayendo texto de {nombre_fichero}...\n")

            # 1. Extraer
            texto_extraido = extraer_texto(self.archivo_actual)

            # 2. Guardar en SQLite
            doc_id = guardar_documento(nombre_fichero, texto_extraido)
            self.resultado_txt.insert("end", f"✓ Guardado en SQLite (ID: {doc_id})\n")

            # 3. Llamar a Claude
            self.resultado_txt.insert("end", "Consultando a Claude (Simulado)...\n")
            respuesta_ia = llamar_a_claude(texto_extraido)

            # 4. Actualizar BBDD y mostrar
            actualizar_respuesta_claude(doc_id, respuesta_ia)
            self.resultado_txt.insert("end", f"\n--- RESPUESTA ---\n{respuesta_ia}\n")

        except Exception as e:
            self.resultado_txt.insert("end", f"\nERROR: {str(e)}")
        finally:
            self.btn_procesar.configure(state="normal")

if __name__ == "__main__":
    app = AppDemo()
    app.mainloop()