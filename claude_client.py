import os
import json
from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()


# ─────────────────────────────────────────────
# PROMPTS POR TIPO DE PÓLIZA
# ─────────────────────────────────────────────

PROMPT_DETECCION = """
Analiza este texto extraído de una póliza de seguro y determina el tipo.

Texto:
{texto}

Responde ÚNICAMENTE con una de estas palabras exactas (sin explicación):
AUTO
HOGAR
VIDA
SALUD
OTRO
"""

PROMPTS_EXTRACCION = {

    "AUTO": """
Eres un extractor experto de documentos de seguro de automóviles.
El documento puede ser una póliza completa, un certificado de seguro, un suplemento o cualquier otro formato de asegurador.
Extrae TODOS los campos que encuentres y devuelve ÚNICAMENTE un JSON válido.
No añadas explicaciones, markdown ni texto fuera del JSON.
Si un campo no aparece, ponlo a null. No inventes datos.

Reglas de formato:
- Fechas: convierte siempre a formato DD/MM/YYYY
- Importes: solo el número sin símbolo de moneda ni puntos de miles (ej: 50000000)
- Garantías: extrae TODAS las que aparezcan, incluyendo asistencia en viaje,
  accidentes del conductor, protección jurídica, defensa multas, rotura de lunas, etc.
  Si el límite dice "Incluida", pon capital_asegurado null e incluida true.
  Usa descripcion_limite para límites con texto (ej: "150 km / gastos custodia 100€").
- Si el tomador y el conductor autorizado son la misma persona, rellena ambas secciones.

Texto del documento:
{texto}

Devuelve este JSON:
{{
  "poliza": {{
    "numero_poliza": null,
    "suplemento": null,
    "tipo_documento": null,
    "efecto": null,
    "vencimiento": null,
    "duracion": null,
    "forma_pago": null,
    "opcion_cobertura": null,
    "fecha_emision": null,
    "lugar_emision": null
  }},
  "asegurador": {{
    "nombre": null,
    "cif": null,
    "direccion": null,
    "ciudad": null,
    "cp": null,
    "email_dpo": null,
    "web": null
  }},
  "centro_reale": {{
    "codigo": null,
    "nombre": null,
    "direccion": null,
    "telefono": null,
    "fax": null,
    "email": null
  }},
  "mediador": {{
    "codigo": null,
    "nombre": null,
    "tipo": null,
    "direccion": null,
    "telefono": null,
    "email": null
  }},
  "tomador": {{
    "nombre": null,
    "apellidos": null,
    "nif": null,
    "direccion": null,
    "ciudad": null,
    "cp": null,
    "email": null,
    "fecha_nacimiento": null
  }},
  "vehiculo": {{
    "matricula": null,
    "tipo": null,
    "marca": null,
    "modelo": null,
    "uso": null,
    "fecha_matriculacion": null,
    "tiene_alarma": null,
    "garaje": null,
    "km_anuales": null,
    "num_plazas": null,
    "combustible": null
  }},
  "accesorios": [
    {{
      "descripcion": null,
      "valor": null,
      "incluido": null
    }}
  ],
  "conductores": [
    {{
      "nombre": null,
      "apellidos": null,
      "nif": null,
      "fecha_nacimiento": null,
      "fecha_carnet": null,
      "puntos_carnet": null,
      "sexo": null,
      "estado_civil": null,
      "ocupacion": null,
      "cp": null,
      "tipo_conductor": null
    }}
  ],
  "recibo": {{
    "tipo": null,
    "periodo_inicio": null,
    "periodo_fin": null,
    "prima": null,
    "consorcio": null,
    "dgs": null,
    "impuestos": null,
    "total": null
  }},
  "domiciliacion": {{
    "banco": null,
    "iban": null,
    "bic": null,
    "tipo_pago": null,
    "referencia_mandato": null,
    "fecha_firma": null,
    "lugar_firma": null
  }},
  "garantias": [
    {{
      "nombre": null,
      "categoria": null,
      "capital_asegurado": null,
      "incluida": null,
      "territorio": null,
      "descripcion_limite": null
    }}
  ]
}}
""",


    "HOGAR": """
Eres un extractor de datos de pólizas de seguro de hogar.
Extrae todos los campos posibles y devuelve ÚNICAMENTE un JSON válido,
sin explicaciones, sin markdown, sin texto adicional.

Texto:
{texto}

Devuelve este JSON (pon null si no encuentras el campo):
{{
  "poliza": {{
    "numero_poliza": null,
    "suplemento": null,
    "efecto": null,
    "vencimiento": null,
    "duracion": null,
    "forma_pago": null,
    "modalidad": null
  }},
  "asegurador": {{
    "nombre": null,
    "cif": null,
    "direccion": null,
    "ciudad": null
  }},
  "mediador": {{
    "codigo": null,
    "nombre": null,
    "telefono": null,
    "email": null
  }},
  "tomador": {{
    "nombre": null,
    "apellidos": null,
    "nif": null,
    "direccion": null,
    "ciudad": null,
    "cp": null,
    "email": null
  }},
  "inmueble": {{
    "direccion": null,
    "ciudad": null,
    "cp": null,
    "tipo": null,
    "uso": null,
    "metros_cuadrados": null,
    "anio_construccion": null,
    "num_plantas": null,
    "tiene_alarma": null,
    "tipo_construccion": null
  }},
  "capitales": {{
    "continente": null,
    "contenido": null,
    "rc_privada": null,
    "valor_reconstruccion": null
  }},
  "recibo": {{
    "tipo": null,
    "periodo_inicio": null,
    "periodo_fin": null,
    "prima": null,
    "impuestos": null,
    "total": null
  }},
  "domiciliacion": {{
    "banco": null,
    "iban": null,
    "tipo_pago": null
  }},
  "garantias": [
    {{
      "nombre": null,
      "capital_asegurado": null,
      "incluida": null,
      "franquicia": null
    }}
  ]
}}
""",

    "VIDA": """
Eres un extractor de datos de pólizas de seguro de vida.
Extrae todos los campos posibles y devuelve ÚNICAMENTE un JSON válido,
sin explicaciones, sin markdown, sin texto adicional.

Texto:
{texto}

Devuelve este JSON (pon null si no encuentras el campo):
{{
  "poliza": {{
    "numero_poliza": null,
    "efecto": null,
    "vencimiento": null,
    "duracion": null,
    "forma_pago": null,
    "modalidad": null
  }},
  "asegurador": {{
    "nombre": null,
    "cif": null,
    "direccion": null
  }},
  "tomador": {{
    "nombre": null,
    "apellidos": null,
    "nif": null,
    "fecha_nacimiento": null,
    "sexo": null,
    "email": null
  }},
  "asegurado": {{
    "nombre": null,
    "apellidos": null,
    "nif": null,
    "fecha_nacimiento": null,
    "sexo": null,
    "profesion": null,
    "fumador": null
  }},
  "beneficiarios": [
    {{
      "nombre": null,
      "nif": null,
      "porcentaje": null,
      "parentesco": null
    }}
  ],
  "capitales": {{
    "fallecimiento": null,
    "invalidez_absoluta": null,
    "invalidez_parcial": null,
    "enfermedad_grave": null
  }},
  "recibo": {{
    "prima": null,
    "impuestos": null,
    "total": null,
    "periodo": null
  }},
  "domiciliacion": {{
    "banco": null,
    "iban": null,
    "tipo_pago": null
  }},
  "garantias": [
    {{
      "nombre": null,
      "capital_asegurado": null,
      "incluida": null
    }}
  ]
}}
""",

    "SALUD": """
Eres un extractor de datos de pólizas de seguro de salud.
Extrae todos los campos posibles y devuelve ÚNICAMENTE un JSON válido,
sin explicaciones, sin markdown, sin texto adicional.

Texto:
{texto}

Devuelve este JSON (pon null si no encuentras el campo):
{{
  "poliza": {{
    "numero_poliza": null,
    "efecto": null,
    "vencimiento": null,
    "duracion": null,
    "forma_pago": null,
    "modalidad": null
  }},
  "asegurador": {{
    "nombre": null,
    "cif": null,
    "direccion": null
  }},
  "tomador": {{
    "nombre": null,
    "apellidos": null,
    "nif": null,
    "fecha_nacimiento": null,
    "email": null
  }},
  "asegurados": [
    {{
      "nombre": null,
      "apellidos": null,
      "nif": null,
      "fecha_nacimiento": null,
      "sexo": null,
      "parentesco": null
    }}
  ],
  "cobertura": {{
    "tipo_cuadro_medico": null,
    "ambito_territorial": null,
    "copago": null,
    "dental_incluido": null,
    "optica_incluida": null
  }},
  "recibo": {{
    "prima": null,
    "impuestos": null,
    "total": null,
    "periodo": null
  }},
  "domiciliacion": {{
    "banco": null,
    "iban": null,
    "tipo_pago": null
  }},
  "garantias": [
    {{
      "nombre": null,
      "capital_asegurado": null,
      "incluida": null,
      "copago": null
    }}
  ]
}}
""",

    "OTRO": """
Eres un extractor de datos de documentos de seguro.
Extrae todos los campos posibles y devuelve ÚNICAMENTE un JSON válido,
sin explicaciones, sin markdown, sin texto adicional.

Texto:
{texto}

Devuelve este JSON con los campos que encuentres:
{{
  "poliza": {{
    "numero_poliza": null,
    "efecto": null,
    "vencimiento": null,
    "forma_pago": null
  }},
  "asegurador": {{
    "nombre": null,
    "cif": null,
    "direccion": null
  }},
  "tomador": {{
    "nombre": null,
    "apellidos": null,
    "nif": null,
    "email": null
  }},
  "recibo": {{
    "prima": null,
    "total": null
  }},
  "campos_extra": {{}}
}}
"""
}


# ─────────────────────────────────────────────
# FUNCIONES PRINCIPALES
# ─────────────────────────────────────────────

def _get_cliente():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("No se encontró ANTHROPIC_API_KEY en el fichero .env")
    return Anthropic(api_key=api_key)


def detectar_tipo_poliza(texto: str) -> str:
    """Pregunta a Claude qué tipo de póliza es."""
    try:
        cliente = _get_cliente()
        resp = cliente.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=10,
            messages=[{
                "role": "user",
                "content": PROMPT_DETECCION.format(texto=texto[:4000])
            }]
        )
        tipo = resp.content[0].text.strip().upper()
        return tipo if tipo in PROMPTS_EXTRACCION else "OTRO"
    except Exception:
        return "OTRO"


def extraer_datos_poliza(texto: str, tipo: str) -> dict:
    """Llama a Claude con el prompt específico y devuelve un dict limpio."""
    try:
        cliente = _get_cliente()
        prompt = PROMPTS_EXTRACCION[tipo].format(texto=texto[:14000])

        resp = cliente.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            messages=[{
                "role": "user",
                "content": prompt
            }]
        )

        texto_respuesta = resp.content[0].text.strip()

        # Limpiar posibles bloques markdown que se cuelen
        if texto_respuesta.startswith("```"):
            lineas = texto_respuesta.split("\n")
            texto_respuesta = "\n".join(lineas[1:-1])

        return json.loads(texto_respuesta)

    except json.JSONDecodeError as e:
        return {"error": f"Claude no devolvió JSON válido: {str(e)}"}
    except Exception as e:
        return {"error": str(e)}


def procesar_pdf_completo(texto: str) -> tuple[str, dict]:
    """
    Función principal que llama la GUI.
    Devuelve (tipo_poliza, datos_extraidos).
    """
    tipo = detectar_tipo_poliza(texto)
    datos = extraer_datos_poliza(texto, tipo)
    return tipo, datos