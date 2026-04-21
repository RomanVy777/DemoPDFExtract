import os
from dotenv import load_dotenv

load_dotenv()

def llamar_a_claude(texto_extraido):
    api_key = os.getenv("ANTHROPIC_API_KEY")

    #Si la clave es la falsa o no existe
    if not api_key or api_key == "tu_clave_aqui_falsa":
        return ("--- MODO DEMO (SIN API KEY) ---\n"
                "Simulación de Claude Sonnet: He leído el PDF correctamente. "
                "El texto extraído empieza así: " + texto_extraido[:100] + "...")

    # MODO REAL: Aquí iría la conexión con la librería Anthropic (la haremos luego)
    return "Conexión real pendiente de configurar con la API Key válida."