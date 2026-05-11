"""
pdf_manager.py — Extracción robusta de texto de PDFs

Estrategias en orden de preferencia:
  1. pdfplumber  (mejor para PDFs con tablas y layout complejo)
  2. pypdf       (fallback rápido para PDFs estándar)
  3. pdfminer    (fallback profundo, mejor con PDFs con encoding raro)
  4. OCR con pytesseract + pdf2image (para PDFs escaneados / imagen)

Si ninguna estrategia extrae texto útil se lanza ValueError descriptivo.
"""

import re


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _tiene_texto_util(texto, minimo_caracteres=50):
    """Comprueba que el texto extraído tiene contenido real, no solo espacios/saltos."""
    if not texto:
        return False
    limpio = re.sub(r"[\s\n\r\t]+", "", texto)
    return len(limpio) >= minimo_caracteres


def _limpiar_texto(texto):
    """Elimina líneas completamente vacías repetidas y espacios sobrantes."""
    if not texto:
        return ""
    # Normalizar saltos de línea múltiples a máximo 2
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    # Eliminar espacios al principio/final de cada línea
    lineas = [l.rstrip() for l in texto.splitlines()]
    return "\n".join(lineas).strip()


# ─────────────────────────────────────────────
# ESTRATEGIA 1: pdfplumber
# ─────────────────────────────────────────────

def _extraer_con_pdfplumber(ruta_pdf):
    import pdfplumber

    texto_total = ""

    with pdfplumber.open(ruta_pdf) as pdf:
        for numero_pagina, pagina in enumerate(pdf.pages, start=1):

            # Intentar primero sin layout (más fiable para PDFs con columnas)
            texto_pagina = pagina.extract_text(
                x_tolerance=3,
                y_tolerance=3,
                layout=False
            ) or ""

            # Si el resultado es pobre, intentar con layout=True
            if not _tiene_texto_util(texto_pagina, 20):
                texto_pagina = pagina.extract_text(
                    x_tolerance=1,
                    y_tolerance=3,
                    layout=True
                ) or ""

            texto_total += f"\n\n--- PAGINA {numero_pagina} ---\n"
            texto_total += texto_pagina

            # Extraer tablas además del texto
            try:
                tablas = pagina.extract_tables()
                if tablas:
                    texto_total += f"\n\n--- TABLAS DETECTADAS PAGINA {numero_pagina} ---\n"
                    for tabla in tablas:
                        for fila in tabla:
                            fila_limpia = []
                            for celda in fila:
                                if celda is None:
                                    fila_limpia.append("")
                                else:
                                    fila_limpia.append(str(celda).strip())
                            texto_total += " | ".join(fila_limpia) + "\n"
            except Exception:
                pass  # Las tablas son opcionales; seguimos aunque fallen

    return texto_total.strip()


# ─────────────────────────────────────────────
# ESTRATEGIA 2: pypdf
# ─────────────────────────────────────────────

def _extraer_con_pypdf(ruta_pdf):
    from pypdf import PdfReader

    lector = PdfReader(ruta_pdf)
    texto_total = ""

    for numero_pagina, pagina in enumerate(lector.pages, start=1):
        texto_pagina = pagina.extract_text() or ""
        texto_total += f"\n\n--- PAGINA {numero_pagina} ---\n"
        texto_total += texto_pagina

    return texto_total.strip()


# ─────────────────────────────────────────────
# ESTRATEGIA 3: pdfminer (mejor con encodings raros)
# ─────────────────────────────────────────────

def _extraer_con_pdfminer(ruta_pdf):
    from pdfminer.high_level import extract_text as pdfminer_extract
    texto = pdfminer_extract(ruta_pdf)
    return (texto or "").strip()


# ─────────────────────────────────────────────
# ESTRATEGIA 4: OCR (para PDFs escaneados / imagen)
# ─────────────────────────────────────────────

def _extraer_con_ocr(ruta_pdf):
    """
    Convierte cada página del PDF a imagen y aplica OCR con tesseract.
    Requiere: pdf2image, pytesseract, y tesseract instalado en el sistema.
    El idioma 'spa' (español) mejora notablemente el reconocimiento.
    """
    from pdf2image import convert_from_path
    import pytesseract

    imagenes = convert_from_path(ruta_pdf, dpi=300)
    texto_total = ""

    for numero_pagina, imagen in enumerate(imagenes, start=1):
        # Intentar con español; si falla, sin especificar idioma
        try:
            texto_pagina = pytesseract.image_to_string(imagen, lang="spa")
        except Exception:
            texto_pagina = pytesseract.image_to_string(imagen)

        texto_total += f"\n\n--- PAGINA {numero_pagina} (OCR) ---\n"
        texto_total += texto_pagina

    return texto_total.strip()


# ─────────────────────────────────────────────
# FUNCIÓN PRINCIPAL
# ─────────────────────────────────────────────

def extraer_texto(ruta_pdf):
    """
    Intenta extraer texto de un PDF usando múltiples estrategias.
    Devuelve el mejor resultado disponible.
    Lanza ValueError si ninguna estrategia obtiene texto útil.
    """
    errores = []

    # ── Estrategia 1: pdfplumber ──────────────
    try:
        texto = _extraer_con_pdfplumber(ruta_pdf)
        if _tiene_texto_util(texto):
            return _limpiar_texto(texto)
    except Exception as e:
        errores.append(f"pdfplumber: {e}")

    # ── Estrategia 2: pypdf ───────────────────
    try:
        texto = _extraer_con_pypdf(ruta_pdf)
        if _tiene_texto_util(texto):
            return _limpiar_texto(texto)
    except Exception as e:
        errores.append(f"pypdf: {e}")

    # ── Estrategia 3: pdfminer ────────────────
    try:
        texto = _extraer_con_pdfminer(ruta_pdf)
        if _tiene_texto_util(texto):
            return _limpiar_texto(texto)
    except Exception as e:
        errores.append(f"pdfminer: {e}")

    # ── Estrategia 4: OCR ─────────────────────
    try:
        texto = _extraer_con_ocr(ruta_pdf)
        if _tiene_texto_util(texto):
            return _limpiar_texto(texto)
        else:
            errores.append("OCR: texto extraído insuficiente (¿PDF en blanco o protegido?)")
    except ImportError:
        errores.append(
            "OCR no disponible: instala 'pdf2image' y 'pytesseract' y asegúrate de tener "
            "Tesseract en el sistema (apt install tesseract-ocr tesseract-ocr-spa)"
        )
    except Exception as e:
        errores.append(f"OCR: {e}")

    # Si llegamos aquí, nada funcionó
    detalle = " | ".join(errores)
    raise ValueError(
        f"No se pudo extraer texto del PDF tras intentar todas las estrategias. "
        f"Detalle: {detalle}"
    )