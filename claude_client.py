import os
import json
from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()


# ─────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────

MODELO_CLAUDE = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")

# Importante: no poner 12000 para tu límite actual
MAX_TOKENS_SALIDA = int(os.getenv("CLAUDE_MAX_TOKENS", "4000"))

# Para que sea rápido, por defecto solo hacemos una pasada
MODO_AGRESIVO = os.getenv("CLAUDE_MODO_AGRESIVO", "false").lower() == "true"

# Límite de caracteres por bloque enviado a Claude
MAX_CARACTERES_ENTRADA = int(os.getenv("CLAUDE_MAX_CARACTERES_ENTRADA", "9000"))


# ─────────────────────────────────────────────
# CLIENTE
# ─────────────────────────────────────────────

def _get_cliente():
    api_key = os.getenv("ANTHROPIC_API_KEY")

    if not api_key:
        raise ValueError("No se encontró ANTHROPIC_API_KEY en el fichero .env")

    return Anthropic(api_key=api_key)


# ─────────────────────────────────────────────
# HERRAMIENTA ESTRUCTURADA
# ─────────────────────────────────────────────

def _herramienta_extraccion():
    return [
        {
            "name": "registrar_extraccion_seguro",
            "description": "Registra una extracción estructurada de un documento de seguros para crear tablas dinámicas en MySQL.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "tipo_seguro": {
                        "type": "string",
                        "description": "Tipo de seguro detectado"
                    },
                    "descripcion": {
                        "type": "string",
                        "description": "Descripción breve del documento"
                    },
                    "tablas": {
                        "type": "object",
                        "description": "Tablas dinámicas detectadas en el documento"
                    }
                },
                "required": ["tipo_seguro", "descripcion", "tablas"]
            }
        }
    ]


def _obtener_tool_input(respuesta):
    for bloque in respuesta.content:
        if getattr(bloque, "type", None) == "tool_use":
            if getattr(bloque, "name", None) == "registrar_extraccion_seguro":
                return bloque.input

    texto = ""

    for bloque in respuesta.content:
        if hasattr(bloque, "text"):
            texto += bloque.text

    if texto.strip():
        return _extraer_json_desde_texto(texto)

    raise ValueError("Claude no devolvió datos estructurados.")


def _extraer_json_desde_texto(texto):
    texto = texto.strip()

    if texto.startswith("```json"):
        texto = texto.replace("```json", "", 1).strip()

    if texto.startswith("```"):
        texto = texto.replace("```", "", 1).strip()

    if texto.endswith("```"):
        texto = texto[:-3].strip()

    inicio = texto.find("{")
    fin = texto.rfind("}")

    if inicio == -1 or fin == -1:
        raise ValueError("Claude no devolvió JSON válido.")

    return json.loads(texto[inicio:fin + 1])


# ─────────────────────────────────────────────
# PROMPTS
# ─────────────────────────────────────────────

def _recortar_texto(texto):
    if not texto:
        return ""

    texto = str(texto)

    if len(texto) > MAX_CARACTERES_ENTRADA:
        texto = texto[:MAX_CARACTERES_ENTRADA]

    return texto


def _prompt_extraccion(texto_apoyo):
    texto_apoyo = _recortar_texto(texto_apoyo)

    return f"""
Eres un extractor experto de pólizas de seguros.

Analiza el siguiente fragmento de texto de una póliza y extrae todos los datos reales que aparezcan.

REGLAS:
- No inventes datos.
- No pongas campos con null.
- No pongas campos vacíos.
- Extrae números de póliza, fechas, importes, tomador, asegurado, vehículo, matrícula, mediador, coberturas, garantías, recibos, franquicias y cualquier dato útil.
- Si encuentras una tabla, conviértela en una lista de objetos.
- Si no sabes clasificar un dato, guárdalo en campos_detectados.
- Cada cobertura o garantía debe ser una fila independiente.
- Cada persona debe ser una fila independiente si hay varias.
- Cada vehículo debe ser una fila independiente si hay varios.
- Devuelve siempre el resultado usando la herramienta registrar_extraccion_seguro.

ESTRUCTURA ESPERADA:
{{
  "tipo_seguro": "AUTO | HOGAR | VIDA | SALUD | DECESOS | COMERCIO | COMUNIDAD | RESPONSABILIDAD_CIVIL | OTRO",
  "descripcion": "descripción breve",
  "tablas": {{
    "documento": {{}},
    "poliza": {{}},
    "aseguradora": {{}},
    "tomador": {{}},
    "asegurado": {{}},
    "mediador": {{}},
    "vehiculo": {{}},
    "garantias": [],
    "coberturas": [],
    "recibos": [],
    "domiciliacion": {{}},
    "campos_detectados": []
  }}
}}

IMPORTANTE:
La tabla campos_detectados debe incluir pares etiqueta/valor encontrados en el texto.

Texto del fragmento:
\"\"\"
{texto_apoyo}
\"\"\"
"""


def _prompt_auditoria(texto_apoyo, datos_primera_pasada):
    texto_apoyo = _recortar_texto(texto_apoyo)

    return f"""
Eres un auditor de extracción de datos de seguros.

Ya existe una primera extracción. Revisa el mismo fragmento y añade campos que falten.

No elimines datos anteriores.
No inventes datos.
Devuelve de nuevo el JSON completo usando la herramienta registrar_extraccion_seguro.

Extracción anterior:
{json.dumps(datos_primera_pasada, ensure_ascii=False)[:6000]}

Texto del fragmento:
\"\"\"
{texto_apoyo}
\"\"\"
"""


# ─────────────────────────────────────────────
# LLAMADA A CLAUDE
# ─────────────────────────────────────────────

def _llamar_claude(prompt):
    cliente = _get_cliente()

    respuesta = cliente.messages.create(
        model=MODELO_CLAUDE,
        max_tokens=MAX_TOKENS_SALIDA,
        temperature=0,
        tools=_herramienta_extraccion(),
        tool_choice={
            "type": "tool",
            "name": "registrar_extraccion_seguro"
        },
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    return _obtener_tool_input(respuesta)


# ─────────────────────────────────────────────
# NORMALIZAR Y FUSIONAR RESULTADOS
# ─────────────────────────────────────────────

def _normalizar(datos):
    if not isinstance(datos, dict):
        return {
            "tipo_seguro": "OTRO",
            "descripcion": "Respuesta no válida",
            "tablas": {}
        }

    tipo = str(datos.get("tipo_seguro", "OTRO")).upper()
    descripcion = datos.get("descripcion", "Documento procesado por Claude")
    tablas = datos.get("tablas", {})

    if not isinstance(tablas, dict):
        tablas = {}

    return {
        "tipo_seguro": tipo,
        "descripcion": descripcion,
        "tablas": tablas
    }


def _valor_vacio(valor):
    return valor is None or valor == "" or valor == [] or valor == {}


def _clave_fila(fila):
    if not isinstance(fila, dict):
        return str(fila)

    partes = []

    for clave in sorted(fila.keys()):
        valor = fila.get(clave)

        if not _valor_vacio(valor):
            partes.append(f"{clave}:{valor}")

    return "|".join(partes)


def _fusionar_listas(lista_1, lista_2):
    resultado = []
    vistos = set()

    for fila in lista_1 + lista_2:
        clave = _clave_fila(fila)

        if clave not in vistos:
            resultado.append(fila)
            vistos.add(clave)

    return resultado


def _fusionar_diccionarios(dic_1, dic_2):
    resultado = dict(dic_1)

    for clave, valor_2 in dic_2.items():
        valor_1 = resultado.get(clave)

        if _valor_vacio(valor_1) and not _valor_vacio(valor_2):
            resultado[clave] = valor_2

        elif isinstance(valor_1, dict) and isinstance(valor_2, dict):
            resultado[clave] = _fusionar_diccionarios(valor_1, valor_2)

        elif isinstance(valor_1, list) and isinstance(valor_2, list):
            resultado[clave] = _fusionar_listas(valor_1, valor_2)

        elif clave not in resultado:
            resultado[clave] = valor_2

    return resultado


def _fusionar_extracciones(datos_1, datos_2):
    datos_1 = _normalizar(datos_1)
    datos_2 = _normalizar(datos_2)

    tipo_1 = datos_1.get("tipo_seguro", "OTRO")
    tipo_2 = datos_2.get("tipo_seguro", "OTRO")

    if tipo_1 != "OTRO":
        tipo_final = tipo_1
    else:
        tipo_final = tipo_2

    resultado = {
        "tipo_seguro": tipo_final,
        "descripcion": datos_1.get("descripcion") or datos_2.get("descripcion") or "Documento procesado por Claude",
        "tablas": {}
    }

    tablas_1 = datos_1.get("tablas", {})
    tablas_2 = datos_2.get("tablas", {})

    nombres_tablas = set(tablas_1.keys()) | set(tablas_2.keys())

    for nombre_tabla in nombres_tablas:
        valor_1 = tablas_1.get(nombre_tabla)
        valor_2 = tablas_2.get(nombre_tabla)

        if isinstance(valor_1, list) or isinstance(valor_2, list):
            lista_1 = valor_1 if isinstance(valor_1, list) else ([valor_1] if valor_1 else [])
            lista_2 = valor_2 if isinstance(valor_2, list) else ([valor_2] if valor_2 else [])
            resultado["tablas"][nombre_tabla] = _fusionar_listas(lista_1, lista_2)

        elif isinstance(valor_1, dict) and isinstance(valor_2, dict):
            resultado["tablas"][nombre_tabla] = _fusionar_diccionarios(valor_1, valor_2)

        else:
            if not _valor_vacio(valor_1):
                resultado["tablas"][nombre_tabla] = valor_1
            else:
                resultado["tablas"][nombre_tabla] = valor_2

    return resultado


# ─────────────────────────────────────────────
# FUNCIÓN PRINCIPAL
# ─────────────────────────────────────────────

def procesar_pdf_completo(texto=None, ruta_pdf=None):
    """
    Esta función se llama desde app.py por cada bloque de texto.

    IMPORTANTE:
    - No se envía el PDF completo.
    - No se usa ruta_pdf.
    - Solo se envía el texto del bloque actual.
    """

    try:
        if not texto or str(texto).strip() == "":
            return "OTRO", {
                "tipo_seguro": "OTRO",
                "descripcion": "Bloque vacío",
                "tablas": {}
            }

        prompt_1 = _prompt_extraccion(texto)

        datos_1 = _llamar_claude(prompt_1)
        datos_1 = _normalizar(datos_1)

        if MODO_AGRESIVO:
            prompt_2 = _prompt_auditoria(
                texto_apoyo=texto,
                datos_primera_pasada=datos_1
            )

            datos_2 = _llamar_claude(prompt_2)
            datos_2 = _normalizar(datos_2)

            datos_finales = _fusionar_extracciones(datos_1, datos_2)

        else:
            datos_finales = datos_1

        tipo = datos_finales.get("tipo_seguro", "OTRO")

        if tipo:
            tipo = str(tipo).upper()
        else:
            tipo = "OTRO"

        datos_finales["tipo_seguro"] = tipo

        return tipo, datos_finales

    except Exception as e:
        return "OTRO", {
            "tipo_seguro": "OTRO",
            "descripcion": "Error procesando el bloque con Claude",
            "tablas": {},
            "error": str(e)
        }