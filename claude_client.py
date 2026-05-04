import os
import json
from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()


# ─────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────

MODELO_CLAUDE = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")


# ─────────────────────────────────────────────
# CLIENTE CLAUDE
# ─────────────────────────────────────────────

def _get_cliente():
    api_key = os.getenv("ANTHROPIC_API_KEY")

    if not api_key:
        raise ValueError("No se encontró ANTHROPIC_API_KEY en el fichero .env")

    return Anthropic(api_key=api_key)


# ─────────────────────────────────────────────
# LIMPIEZA DE RESPUESTA
# ─────────────────────────────────────────────

def extraer_json_desde_texto(texto_respuesta):
    """
    Limpia la respuesta de Claude y se queda únicamente con el JSON.
    """

    if not texto_respuesta:
        raise ValueError("Claude devolvió una respuesta vacía.")

    texto = texto_respuesta.strip()

    if texto.startswith("```"):
        lineas = texto.splitlines()

        if len(lineas) >= 3:
            texto = "\n".join(lineas[1:-1]).strip()

    inicio = texto.find("{")
    fin = texto.rfind("}")

    if inicio == -1 or fin == -1:
        raise ValueError("No se encontró ningún JSON en la respuesta de Claude.")

    texto_json = texto[inicio:fin + 1]

    return json.loads(texto_json)


# ─────────────────────────────────────────────
# DETECCIÓN DEL TIPO DE SEGURO
# ─────────────────────────────────────────────

def detectar_tipo_poliza(texto):
    """
    Detecta el tipo de seguro.
    """

    cliente = _get_cliente()

    prompt = f"""
Analiza el siguiente texto extraído de un PDF de seguros.

Tienes que clasificarlo en uno de estos tipos:

AUTO
HOGAR
VIDA
SALUD
DECESOS
COMERCIO
COMUNIDAD
OTRO

Responde únicamente con una palabra de la lista anterior.
No añadas explicación.

Texto:
\"\"\"
{texto[:5000]}
\"\"\"
"""

    respuesta = cliente.messages.create(
        model=MODELO_CLAUDE,
        max_tokens=20,
        temperature=0,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    tipo = respuesta.content[0].text.strip().upper()

    tipos_validos = {
        "AUTO",
        "HOGAR",
        "VIDA",
        "SALUD",
        "DECESOS",
        "COMERCIO",
        "COMUNIDAD",
        "OTRO"
    }

    if tipo not in tipos_validos:
        return "OTRO"

    return tipo


# ─────────────────────────────────────────────
# EXTRACCIÓN DINÁMICA
# ─────────────────────────────────────────────

def extraer_datos_dinamicos(texto, tipo_detectado):
    """
    Claude no usa campos predefinidos.
    Claude decide las tablas y los campos según el PDF.
    """

    cliente = _get_cliente()

    prompt = f"""
Eres un sistema experto en extracción de datos de documentos PDF de seguros.

El texto procede de un PDF de seguro.
El tipo detectado inicialmente es: {tipo_detectado}

Tu tarea es analizar el documento y devolver una estructura de base de datos dinámica.

Muy importante:
- No uses una plantilla fija.
- No uses campos predefinidos.
- No inventes datos.
- No incluyas campos que no aparezcan en el texto.
- No pongas campos con valor null.
- Extrae todos los datos reales que puedas encontrar.
- Agrupa los datos en tablas lógicas.
- Cada sección importante del documento debe ser una tabla.
- Si una sección tiene un solo registro, devuelve un objeto.
- Si una sección tiene varios registros, devuelve una lista de objetos.
- Los nombres de tablas y campos deben estar en español.
- Usa nombres claros y sencillos.
- Devuelve únicamente JSON válido.
- No añadas explicaciones.
- No uses markdown.

Ejemplos de tablas que podrías crear si aparecen en el documento:
- documento
- poliza
- aseguradora
- tomador
- asegurado
- mediador
- vehiculo
- conductores
- garantias
- coberturas
- recibos
- domiciliacion
- capitales
- inmueble
- beneficiarios
- exclusiones
- franquicias
- asistencia
- datos_administrativos
- certificados
- condiciones

Formato obligatorio de respuesta:

{{
  "tipo_seguro": "{tipo_detectado}",
  "descripcion": "descripción breve del documento",
  "tablas": {{
    "nombre_tabla_1": {{
      "campo_1": "valor real encontrado",
      "campo_2": "valor real encontrado"
    }},
    "nombre_tabla_2": [
      {{
        "campo_1": "valor real encontrado",
        "campo_2": "valor real encontrado"
      }},
      {{
        "campo_1": "valor real encontrado",
        "campo_2": "valor real encontrado"
      }}
    ]
  }}
}}

Reglas concretas:
- Si ves datos de la póliza, crea una tabla "poliza".
- Si ves datos del tomador, crea una tabla "tomador".
- Si ves datos del vehículo, crea una tabla "vehiculo".
- Si ves garantías o coberturas, crea una tabla "garantias" o "coberturas" como lista.
- Si ves importes, respeta el importe tal como aparece.
- Si ves fechas, respeta la fecha tal como aparece.
- Si hay varias garantías, cada garantía debe ser un registro distinto dentro de una lista.
- Si hay varios asegurados, cada asegurado debe ser un registro distinto dentro de una lista.
- Si hay varios recibos, cada recibo debe ser un registro distinto dentro de una lista.
- El JSON debe contener obligatoriamente la clave "tablas".
- La clave "tablas" no puede estar vacía si se han encontrado datos.

Texto del PDF:
\"\"\"
{texto[:25000]}
\"\"\"
"""

    respuesta = cliente.messages.create(
        model=MODELO_CLAUDE,
        max_tokens=8000,
        temperature=0,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    texto_respuesta = respuesta.content[0].text.strip()

    datos = extraer_json_desde_texto(texto_respuesta)

    return asegurar_formato_dinamico(datos, tipo_detectado)


# ─────────────────────────────────────────────
# ASEGURAR FORMATO CORRECTO
# ─────────────────────────────────────────────

def asegurar_formato_dinamico(datos, tipo_detectado):
    """
    Garantiza que la respuesta tenga esta forma:

    {
        "tipo_seguro": "...",
        "descripcion": "...",
        "tablas": {...}
    }
    """

    if not isinstance(datos, dict):
        return {
            "tipo_seguro": tipo_detectado,
            "descripcion": "Claude no devolvió un diccionario válido",
            "tablas": {}
        }

    if "tablas" in datos and isinstance(datos["tablas"], dict):
        if "tipo_seguro" not in datos:
            datos["tipo_seguro"] = tipo_detectado

        if "descripcion" not in datos:
            datos["descripcion"] = "Documento procesado por Claude"

        return datos

    tablas = {}

    claves_no_tabla = {
        "tipo_seguro",
        "tipo_poliza",
        "descripcion",
        "error"
    }

    for clave, valor in datos.items():
        if clave not in claves_no_tabla:
            tablas[clave] = valor

    return {
        "tipo_seguro": datos.get("tipo_seguro", tipo_detectado),
        "descripcion": datos.get("descripcion", "Documento procesado por Claude"),
        "tablas": tablas
    }


# ─────────────────────────────────────────────
# FUNCIÓN PRINCIPAL QUE USA LA INTERFAZ
# ─────────────────────────────────────────────

def procesar_pdf_completo(texto):
    """
    Esta es la función que llama tu interfaz.

    Devuelve:
    tipo, datos

    Donde datos ya viene preparado para crear tablas dinámicas.
    """

    try:
        tipo = detectar_tipo_poliza(texto)
        datos = extraer_datos_dinamicos(texto, tipo)

        tipo_final = datos.get("tipo_seguro", tipo)

        if tipo_final:
            tipo_final = tipo_final.upper()
        else:
            tipo_final = tipo

        datos["tipo_seguro"] = tipo_final

        return tipo_final, datos

    except Exception as e:
        return "OTRO", {
            "tipo_seguro": "OTRO",
            "descripcion": "Error procesando el documento con Claude",
            "tablas": {},
            "error": str(e)
        }