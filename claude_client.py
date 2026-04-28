import os
from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()


def llamar_a_claude(texto_extraido):

    api_key = os.getenv("ANTHROPIC_API_KEY")

    if not api_key:
        return "No se encontró API Key"

    try:

        cliente = Anthropic(api_key=api_key)

        respuesta = cliente.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[
                {
                    "role": "user",
                    "content": f"""
Lee este texto extraído de un PDF y extrae información importante.

Texto:

{texto_extraido[:12000]}

Devuelve:
- resumen
- posibles campos encontrados
- información importante
"""
                }
            ]
        )

        return respuesta.content[0].text

    except Exception as e:
        return f"Error Claude: {str(e)}"