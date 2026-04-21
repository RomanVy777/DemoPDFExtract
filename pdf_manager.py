from pypdf import PdfReader

def extraer_texto(ruta_pdf):
    try:
        reader = PdfReader(ruta_pdf)
        texto_completo = ""
        for i, pagina in enumerate(reader.pages):
            cuerpo = pagina.extract_text()
            if cuerpo:
                texto_completo += f"[Página {i+1}]\n{cuerpo}\n"
        return texto_completo
    except Exception as e:
        return f"Error al leer el PDF: {e}"