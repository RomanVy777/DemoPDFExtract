import os
import json
from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()

# ─────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────

# Intentamos leer el modelo del .env, si no, usamos el más reciente de la familia Sonnet
MODELO_CLAUDE = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20240620")

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
    Limpia la respuesta de Claude para extraer solo el bloque JSON.
    """
    if not texto_respuesta:
        raise ValueError("Claude devolvió una respuesta vacía.")

    texto = texto_respuesta.strip()

    # Si viene envuelto en markdown ```json ... ```
    if "```" in texto:
        # Buscamos el contenido entre el primer { y el último }
        inicio = texto.find("{")
        fin = texto.rfind("}")
        if inicio != -1 and fin != -1:
            texto = texto[inicio:fin + 1]

    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        # Intento final por si hay texto antes o después
        inicio = texto.find("{")
        fin = texto.rfind("}")
        if inicio != -1 and fin != -1:
            return json.loads(texto[inicio:fin + 1])
        raise ValueError("La respuesta de Claude no contiene un JSON válido.")

# ─────────────────────────────────────────────
# DETECCIÓN DEL TIPO DE SEGURO
# ─────────────────────────────────────────────

def detectar_tipo_poliza(texto):
    """
    Clasifica rápidamente el documento.
    """
    cliente = _get_cliente()

    prompt = f"""
    Analiza el texto de este seguro y clasifícalo en una de estas categorías:
    AUTO, HOGAR, VIDA, SALUD, DECESOS, COMERCIO, COMUNIDAD, OTRO.
    
    Responde únicamente con la palabra de la categoría.
    
    Texto:
    \"\"\"
    {texto[:5000]}
    \"\"\"
    """

    respuesta = cliente.messages.create(
        model=MODELO_CLAUDE,
        max_tokens=20,
        temperature=0,
        messages=[{"role": "user", "content": prompt}]
    )

    tipo = respuesta.content[0].text.strip().upper()
    tipos_validos = {"AUTO", "HOGAR", "VIDA", "SALUD", "DECESOS", "COMERCIO", "COMUNIDAD", "OTRO"}

    return tipo if tipo in tipos_validos else "OTRO"

# ─────────────────────────────────────────────
# EXTRACCIÓN DINÁMICA
# ─────────────────────────────────────────────

def extraer_datos_dinamicos(texto, tipo_detectado):
    """
    Extrae datos sin plantillas fijas para alimentar la creación de tablas en Oracle.
    """
    cliente = _get_cliente()

    prompt = f"""
    Eres un experto en seguros. Extrae todos los datos relevantes del siguiente texto.
    
    Tipo detectado: {tipo_detectado}

    REGLAS:
    1. Devuelve un JSON con tres claves: "tipo_seguro", "descripcion" y "tablas".
    2. Dentro de "tablas", crea claves para cada sección (ej: "tomador", "vehiculo", "coberturas").
    3. Si una sección tiene varios elementos (como coberturas o recibos), usa una LISTA de objetos.
    4. Usa nombres de campos en ESPAÑOL, claros y sin espacios (usa guiones bajos).
    5. No inventes datos. Si no está, no lo incluyas.
    6. Devuelve ÚNICAMENTE el JSON puro, sin explicaciones ni markdown.

    Formato:
    {{
      "tipo_seguro": "{tipo_detectado}",
      "descripcion": "Breve resumen",
      "tablas": {{
        "nombre_tabla": {{ "campo": "valor" }},
        "lista_tabla": [ {{ "campo": "valor" }}, {{ "campo": "valor" }} ]
      }}
    }}

    Texto:
    \"\"\"
    {texto[:25000]}
    \"\"\"
    """

    respuesta = cliente.messages.create(
        model=MODELO_CLAUDE,
        max_tokens=8000,
        temperature=0,
        messages=[{"role": "user", "content": prompt}]
    )

    return extraer_json_desde_texto(respuesta.content[0].text)

# ─────────────────────────────────────────────
# ASEGURAR FORMATO CORRECTO
# ─────────────────────────────────────────────

def asegurar_formato_dinamico(datos, tipo_detectado):
    """
    Garantiza que la salida sea compatible con la lógica de base de datos dinámica.
    """
    if not isinstance(datos, dict):
        return {"tipo_seguro": tipo_detectado, "descripcion": "Error formato", "tablas": {}}

    # Si Claude puso las tablas en la raíz en lugar de dentro de "tablas"
    if "tablas" not in datos:
        tablas = {}
        excluir = {"tipo_seguro", "descripcion", "analisis"}
        for k, v in datos.items():
            if k not in excluir:
                tablas[k] = v
        datos = {
            "tipo_seguro": datos.get("tipo_seguro", tipo_detectado),
            "descripcion": datos.get("descripcion", "Extraído dinámicamente"),
            "tablas": tablas
        }

    return datos

# ─────────────────────────────────────────────
# FUNCIÓN PRINCIPAL (LLAMADA POR GUI.PY)
# ─────────────────────────────────────────────

def procesar_pdf_completo(texto):
    """
    Punto de entrada principal para la aplicación.
    """
    try:
        tipo = detectar_tipo_poliza(texto)
        datos_raw = extraer_datos_dinamicos(texto, tipo)
        datos_listos = asegurar_formato_dinamico(datos_raw, tipo)

        # Aseguramos que el tipo final esté en mayúsculas
        tipo_final = str(datos_listos.get("tipo_seguro", tipo)).upper()
        datos_listos["tipo_seguro"] = tipo_final

        return tipo_final, datos_listos

    except Exception as e:
        return "OTRO", {
            "tipo_seguro": "OTRO",
            "descripcion": "Error en el proceso",
            "tablas": {},
            "error": str(e)
        }