import customtkinter as ctk
from tkinterdnd2 import DND_FILES, TkinterDnD
from pdf_manager import extraer_texto
from claude_client import procesar_pdf_completo
from database_manager import inicializar_bbdd, guardar_documento, crear_tablas_desde_json_claude
import threading
import json
import time
import re


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


# ─────────────────────────────────────────────
# CONFIGURACIÓN DE RENDIMIENTO
# ─────────────────────────────────────────────

TAMANO_BLOQUE = 15000  # Modificado: Bloque mucho más grande para que entren tablas enteras
SOLAPE_BLOQUE = 1500   # Modificado: Solape mayor para no partir filas por la mitad

MAX_BLOQUES_CLAUDE = 8

ESPERA_ENTRE_BLOQUES = 10
ESPERA_SI_HAY_LIMITE = 65

MAX_INTENTOS_CLAUDE = 2

MAX_LINEAS_INICIALES = 400
MAX_CARACTERES_TEXTO_RELEVANTE = 60000


ICONOS_TIPO = {
    "AUTO": "AUTO",
    "HOGAR": "HOGAR",
    "VIDA": "VIDA",
    "SALUD": "SALUD",
    "DECESOS": "DECESOS",
    "COMERCIO": "COMERCIO",
    "COMUNIDAD": "COMUNIDAD",
    "RESPONSABILIDAD_CIVIL": "RESPONSABILIDAD_CIVIL",
    "OTRO": "OTRO",
}


# ─────────────────────────────────────────────
# FUNCIONES PARA DIVIDIR Y LIMPIAR TEXTO
# ─────────────────────────────────────────────

def dividir_texto(texto, tamano=TAMANO_BLOQUE, solape=SOLAPE_BLOQUE):
    bloques = []
    inicio = 0

    while inicio < len(texto):
        fin = min(inicio + tamano, len(texto))
        bloque = texto[inicio:fin]
        bloques.append(bloque)

        if fin >= len(texto):
            break

        inicio = fin - solape

        if inicio < 0:
            inicio = 0

    return bloques


def limpiar_json_texto(texto):
    if not isinstance(texto, str):
        return texto

    texto = texto.strip()

    if texto.startswith("```json"):
        texto = texto.replace("```json", "", 1).strip()

    if texto.startswith("```"):
        texto = texto.replace("```", "", 1).strip()

    if texto.endswith("```"):
        texto = texto[:-3].strip()

    inicio = texto.find("{")
    fin = texto.rfind("}")

    if inicio != -1 and fin != -1:
        texto = texto[inicio:fin + 1]

    return texto


# ─────────────────────────────────────────────
# FILTRADO INTELIGENTE DE TEXTO RELEVANTE
# ─────────────────────────────────────────────

def normalizar_texto(texto):
    texto = str(texto).lower()

    cambios = {
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "ü": "u",
        "ñ": "n"
    }

    for original, nuevo in cambios.items():
        texto = texto.replace(original, nuevo)

    return texto


def linea_importante(linea):
    linea_normalizada = normalizar_texto(linea)

    palabras_clave = [
        "poliza",
        "nº de poliza",
        "numero de poliza",
        "certificado",
        "suplemento",
        "tomador",
        "asegurado",
        "aseguradora",
        "compania",
        "mediador",
        "agente",
        "vehiculo",
        "matricula",
        "marca",
        "modelo",
        "version",
        "bastidor",
        "taxi",
        "conductor",
        "nif",
        "dni",
        "cif",
        "domicilio",
        "direccion",
        "codigo postal",
        "telefono",
        "email",
        "correo",
        "fecha de efecto",
        "efecto",
        "vencimiento",
        "fecha de vencimiento",
        "fecha de emision",
        "fecha de nacimiento",
        "prima",
        "recibo",
        "importe",
        "total",
        "iban",
        "domiciliacion",
        "forma de pago",
        "garantia",
        "garantias",
        "cobertura",
        "coberturas",
        "responsabilidad civil",
        "defensa juridica",
        "asistencia",
        "lunas",
        "robo",
        "incendio",
        "franquicia",
        "capital",
        "limite",
        "condiciones particulares",
        "condiciones especiales",
        "datos del riesgo",
        "datos bancarios",
        "prima neta",
        "impuestos",
        "consorcio",
        "bonificacion"
    ]

    for palabra in palabras_clave:
        if palabra in linea_normalizada:
            return True

    patrones = [
        r"\b\d{4}\s?[A-Z]{3}\b",
        r"\b[A-Z]{1,2}\s?\d{4}\s?[A-Z]{1,2}\b",
        r"\b\d{8}[A-Z]\b",
        r"\b[A-Z]\d{8}\b",
        r"\bES\d{2}\s?\d{4}\s?\d{4}\s?\d{2}\s?\d{10}\b",
        r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
        r"\b\d{1,2}-\d{1,2}-\d{2,4}\b",
        r"\b\d+[,.]\d{2}\s?€\b",
        r"\b\d+[,.]\d{2}\s?eur\b",
        r"\b\d{6,}\b"
    ]

    for patron in patrones:
        if re.search(patron, linea, re.IGNORECASE):
            return True

    # ¡NUEVO! Conservar siempre las líneas de las tablas generadas por pdf_manager
    if "|" in linea:
        return True

    return False


def construir_texto_relevante(texto):
    lineas_originales = texto.splitlines()
    lineas = [l.strip() for l in lineas_originales if l.strip()]

    texto_completo = "\n".join(lineas)
    if len(texto_completo) <= MAX_CARACTERES_TEXTO_RELEVANTE:
        return texto_completo

    posiciones = set()

    for i in range(min(MAX_LINEAS_INICIALES, len(lineas))):
        posiciones.add(i)

    for i, linea in enumerate(lineas):
        if linea_importante(linea):
            inicio = max(0, i - 5)
            fin = min(len(lineas), i + 6)
            for j in range(inicio, fin):
                posiciones.add(j)

    posiciones_ordenadas = sorted(posiciones)

    resultado = []
    vistos = set()
    caracteres = 0

    for pos in posiciones_ordenadas:
        linea = lineas[pos]
        if linea in vistos:
            continue
        vistos.add(linea)

        if caracteres + len(linea) + 1 > MAX_CARACTERES_TEXTO_RELEVANTE:
            break

        resultado.append(linea)
        caracteres += len(linea) + 1

    return "\n".join(resultado)


def puntuar_bloque(bloque, indice):
    texto = normalizar_texto(bloque)

    palabras_clave = {
        "poliza": 15,
        "certificado": 12,
        "suplemento": 8,
        "tomador": 14,
        "asegurado": 12,
        "aseguradora": 8,
        "compania": 8,
        "mediador": 8,
        "vehiculo": 15,
        "matricula": 18,
        "marca": 8,
        "modelo": 8,
        "bastidor": 12,
        "taxi": 20,
        "conductor": 10,
        "nif": 10,
        "dni": 10,
        "cif": 10,
        "fecha": 6,
        "efecto": 10,
        "vencimiento": 10,
        "prima": 12,
        "recibo": 12,
        "importe": 8,
        "total": 8,
        "iban": 15,
        "garantia": 12,
        "garantias": 12,
        "cobertura": 12,
        "coberturas": 12,
        "responsabilidad civil": 18,
        "franquicia": 10,
        "capital": 8,
        "asistencia": 8,
        "condiciones particulares": 20
    }

    puntos = 0

    for palabra, peso in palabras_clave.items():
        puntos += texto.count(palabra) * peso

    # ¡NUEVO! Da prioridad a los bloques que contienen tablas reales
    puntos += bloque.count("|") * 5

    if indice == 0:
        puntos += 200
    elif indice == 1:
        puntos += 100
    elif indice == 2:
        puntos += 50

    return puntos


def seleccionar_bloques_importantes(bloques):
    if len(bloques) <= MAX_BLOQUES_CLAUDE:
        indices = []

        for i in range(len(bloques)):
            indices.append(i + 1)

        return bloques, indices

    puntuados = []

    for indice, bloque in enumerate(bloques):
        puntos = puntuar_bloque(bloque, indice)
        puntuados.append((puntos, indice, bloque))

    puntuados.sort(reverse=True)

    seleccionados = puntuados[:MAX_BLOQUES_CLAUDE]
    seleccionados.sort(key=lambda x: x[1])

    bloques_finales = []
    indices_finales = []

    for puntos, indice, bloque in seleccionados:
        bloques_finales.append(bloque)
        indices_finales.append(indice + 1)

    return bloques_finales, indices_finales


# ─────────────────────────────────────────────
# APP
# ─────────────────────────────────────────────

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

            self._log_seguro("2. Filtrando texto relevante del PDF...")

            texto_relevante = construir_texto_relevante(texto)

            if not texto_relevante or texto_relevante.strip() == "":
                self._log_seguro("No se ha encontrado texto relevante.")
                self._log_seguro("Se usará el comienzo del documento como alternativa.")
                texto_relevante = texto[:MAX_CARACTERES_TEXTO_RELEVANTE]

            self._log_seguro(f"Texto original: {len(texto):,} caracteres")
            self._log_seguro(f"Texto enviado a Claude: {len(texto_relevante):,} caracteres")

            porcentaje = (len(texto_relevante) * 100) / len(texto)
            reduccion = 100 - porcentaje

            self._log_seguro(f"Reducción aproximada: {reduccion:.2f}%\n")

            self._log_seguro("3. Dividiendo texto relevante en bloques...")

            bloques = dividir_texto(texto_relevante)

            self._log_seguro(f"Bloques generados sobre texto relevante: {len(bloques)}")
            self._log_seguro(f"Tamaño aproximado por bloque: {TAMANO_BLOQUE:,} caracteres\n")

            self._log_seguro("4. Seleccionando bloques más importantes...")

            bloques_importantes, indices_bloques = seleccionar_bloques_importantes(bloques)

            self._log_seguro(
                f"Bloques que se enviarán a Claude: {len(bloques_importantes)} de {len(bloques)}"
            )

            self._log_seguro(f"Bloques seleccionados: {indices_bloques}\n")

            self._log_seguro("5. Enviando bloques importantes a Claude...")

            tipo, datos = self._procesar_bloques_con_claude(bloques_importantes)

            if not datos:
                self._log_seguro("Claude no ha devuelto datos válidos.")
                return

            if "error" in datos:
                self._log_seguro(f"Claude devolvió un error: {datos['error']}")
                return

            datos = self._asegurar_formato_dinamico(tipo, datos)

            tipo = datos.get("tipo_seguro", tipo or "OTRO")
            tipo = str(tipo).upper()

            self._log_seguro(f"\nTipo de seguro detectado: {tipo}\n")
            self._configurar_badge(tipo)

            if "tablas" not in datos:
                self._log_seguro("El JSON de Claude no contiene la clave 'tablas'.")
                self._log_seguro("JSON recibido:")
                self._log_seguro(json.dumps(datos, ensure_ascii=False, indent=4))
                return

            self._log_seguro("6. Guardando documento principal en MySQL...")

            id_documento = guardar_documento(
                nombre_archivo=nombre,
                tipo_seguro=tipo,
                texto_extraido=texto,
                datos_claude=datos
            )

            self._log_seguro(f"Documento guardado con ID: {id_documento}\n")

            self._log_seguro("7. Creando tablas dinámicas en MySQL...")

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

    def _procesar_bloques_con_claude(self, bloques):
        resultado_final = {
            "tipo_seguro": "OTRO",
            "descripcion": "Documento procesado por Claude por bloques relevantes",
            "tablas": {}
        }

        bloques_correctos = 0

        for indice, bloque in enumerate(bloques):
            self._log_seguro(f"Procesando bloque {indice + 1} de {len(bloques)}...")

            datos_bloque = None
            tipo_bloque = "OTRO"

            for intento in range(1, MAX_INTENTOS_CLAUDE + 1):
                try:
                    respuesta_claude = procesar_pdf_completo(
                        texto=bloque,
                        ruta_pdf=None
                    )

                    tipo_bloque, datos_bloque = self._normalizar_respuesta_claude(respuesta_claude)

                    if datos_bloque and "error" not in datos_bloque:
                        break

                    if datos_bloque and "error" in datos_bloque:
                        mensaje_error = str(datos_bloque["error"])

                        if "rate_limit_error" in mensaje_error or "429" in mensaje_error:
                            self._log_seguro(
                                f"Bloque {indice + 1}: límite de Claude alcanzado."
                            )
                            self._log_seguro(
                                f"Esperando {ESPERA_SI_HAY_LIMITE} segundos antes de reintentar..."
                            )
                            time.sleep(ESPERA_SI_HAY_LIMITE)
                        else:
                            self._log_seguro(f"Bloque {indice + 1}: error de Claude.")
                            self._log_seguro(mensaje_error)
                            break

                except Exception as e:
                    mensaje_error = str(e)

                    if "rate_limit_error" in mensaje_error or "429" in mensaje_error:
                        self._log_seguro(
                            f"Bloque {indice + 1}: límite de Claude en el intento {intento}."
                        )
                        self._log_seguro(
                            f"Esperando {ESPERA_SI_HAY_LIMITE} segundos antes de reintentar..."
                        )
                        time.sleep(ESPERA_SI_HAY_LIMITE)
                    else:
                        self._log_seguro(f"Bloque {indice + 1}: error inesperado.")
                        self._log_seguro(mensaje_error)
                        break

            if not datos_bloque:
                self._log_seguro(f"Bloque {indice + 1}: no se pudo procesar.")
                continue

            if "error" in datos_bloque:
                self._log_seguro(f"Bloque {indice + 1}: no se pudo procesar correctamente.")
                continue

            datos_bloque = self._asegurar_formato_dinamico(tipo_bloque, datos_bloque)

            tipo_detectado = datos_bloque.get("tipo_seguro", tipo_bloque or "OTRO")
            tipo_detectado = str(tipo_detectado).upper()

            if resultado_final["tipo_seguro"] == "OTRO" and tipo_detectado != "OTRO":
                resultado_final["tipo_seguro"] = tipo_detectado

            self._fusionar_jsons(resultado_final, datos_bloque)
            bloques_correctos += 1

            self._log_seguro(f"Bloque {indice + 1}: procesado correctamente.")

            if indice < len(bloques) - 1:
                self._log_seguro(
                    f"Esperando {ESPERA_ENTRE_BLOQUES} segundos antes del siguiente bloque..."
                )
                time.sleep(ESPERA_ENTRE_BLOQUES)

        if bloques_correctos == 0:
            return "OTRO", {
                "error": "No se pudo procesar ningún bloque correctamente."
            }

        return resultado_final.get("tipo_seguro", "OTRO"), resultado_final

    def _normalizar_respuesta_claude(self, respuesta):
        if isinstance(respuesta, tuple):
            tipo, datos = respuesta

            if isinstance(datos, str):
                datos = self._convertir_texto_a_json(datos)

            if isinstance(datos, dict):
                if "tipo_seguro" not in datos:
                    datos["tipo_seguro"] = tipo

                return tipo, datos

        if isinstance(respuesta, dict):
            tipo = respuesta.get("tipo_seguro", "OTRO")
            return tipo, respuesta

        if isinstance(respuesta, str):
            datos = self._convertir_texto_a_json(respuesta)

            if isinstance(datos, dict):
                tipo = datos.get("tipo_seguro", "OTRO")
                return tipo, datos

        return "OTRO", {}

    def _convertir_texto_a_json(self, texto):
        try:
            texto_limpio = limpiar_json_texto(texto)
            return json.loads(texto_limpio)
        except Exception:
            return {
                "error": "Claude no devolvió un JSON válido",
                "respuesta_original": texto
            }

    def _asegurar_formato_dinamico(self, tipo, datos):
        if not isinstance(datos, dict):
            return {
                "tipo_seguro": tipo or "OTRO",
                "descripcion": "Respuesta no válida",
                "tablas": {}
            }

        if "error" in datos:
            return {
                "tipo_seguro": tipo or datos.get("tipo_seguro") or "OTRO",
                "descripcion": "Error devuelto por Claude",
                "tablas": {},
                "error": datos.get("error")
            }

        if "tablas" in datos and isinstance(datos["tablas"], dict):
            if "tipo_seguro" not in datos:
                datos["tipo_seguro"] = tipo or "OTRO"

            if "descripcion" not in datos:
                datos["descripcion"] = "Documento procesado por Claude"

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

    def _fusionar_jsons(self, destino, nuevo):
        if not isinstance(nuevo, dict):
            return

        if destino.get("tipo_seguro") == "OTRO":
            tipo_nuevo = nuevo.get("tipo_seguro", "OTRO")
            tipo_nuevo = str(tipo_nuevo).upper()

            if tipo_nuevo != "OTRO":
                destino["tipo_seguro"] = tipo_nuevo

        if not destino.get("descripcion") and nuevo.get("descripcion"):
            destino["descripcion"] = nuevo.get("descripcion")

        tablas_destino = destino.get("tablas", {})
        tablas_nuevas = nuevo.get("tablas", {})

        if not isinstance(tablas_nuevas, dict):
            return

        for nombre_tabla, contenido_nuevo in tablas_nuevas.items():
            if nombre_tabla not in tablas_destino:
                tablas_destino[nombre_tabla] = contenido_nuevo
            else:
                tablas_destino[nombre_tabla] = self._fusionar_contenido_tabla(
                    tablas_destino[nombre_tabla],
                    contenido_nuevo
                )

        destino["tablas"] = tablas_destino

    def _fusionar_contenido_tabla(self, existente, nuevo):
        if isinstance(existente, dict) and isinstance(nuevo, dict):
            return self._fusionar_diccionarios(existente, nuevo)

        if isinstance(existente, list) and isinstance(nuevo, list):
            return self._fusionar_listas(existente, nuevo)

        if isinstance(existente, list) and isinstance(nuevo, dict):
            if not self._existe_en_lista(existente, nuevo):
                existente.append(nuevo)

            return existente

        if isinstance(existente, dict) and isinstance(nuevo, list):
            lista = [existente]

            for elemento in nuevo:
                if not self._existe_en_lista(lista, elemento):
                    lista.append(elemento)

            return lista

        if self._valor_vacio(existente) and not self._valor_vacio(nuevo):
            return nuevo

        return existente

    def _fusionar_diccionarios(self, existente, nuevo):
        for clave, valor_nuevo in nuevo.items():
            if clave not in existente:
                existente[clave] = valor_nuevo
            else:
                valor_existente = existente[clave]

                if self._valor_vacio(valor_existente) and not self._valor_vacio(valor_nuevo):
                    existente[clave] = valor_nuevo

                elif isinstance(valor_existente, dict) and isinstance(valor_nuevo, dict):
                    existente[clave] = self._fusionar_diccionarios(valor_existente, valor_nuevo)

                elif isinstance(valor_existente, list) and isinstance(valor_nuevo, list):
                    existente[clave] = self._fusionar_listas(valor_existente, valor_nuevo)

        return existente

    def _fusionar_listas(self, existente, nuevo):
        for elemento in nuevo:
            if not self._existe_en_lista(existente, elemento):
                existente.append(elemento)

        return existente

    def _existe_en_lista(self, lista, elemento):
        for item in lista:
            if item == elemento:
                return True

        return False

    def _valor_vacio(self, valor):
        return valor is None or valor == "" or valor == [] or valor == {}

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
                self._log_seguro("  Registros: 1")
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