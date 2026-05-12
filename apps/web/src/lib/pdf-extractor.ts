// apps/web/src/lib/pdf-extractor.ts
// ─────────────────────────────────────────────────────────────────────────────
// MOTOR DE EXTRACCIÓN DE TEXTO DE PDFs
//
// TRADUCCIÓN COMPLETA DE: pdf_manager.py
//
// DIFERENCIAS DE PARADIGMA (Python → TypeScript):
//
// 1. LIBRERÍAS:
//    Python: pdfplumber → Node.js: pdf-parse (extracción directa de texto)
//    Python: pypdf      → Node.js: pdf-parse (mismo paquete, estrategia alternativa)
//    Python: pdfminer   → Node.js: pdf-parse con opciones más permisivas
//    Python: pytesseract + pdf2image → Node.js: tesseract.js (OCR puro JS,
//            sin dependencias del sistema operativo como en Python)
//
// 2. SINCRONISMO:
//    Python: funciones síncronas con open() y bucles for
//    TypeScript: todo async/await, el Buffer de Node.js reemplaza a ruta_pdf
//
// 3. BUFFER vs RUTA:
//    En Python se pasaba ruta_pdf (string del filesystem).
//    En Node.js/Next.js, el PDF llega como Buffer desde el upload del navegador.
//    Esto elimina la necesidad de escribir el PDF a disco temporalmente.
//
// 4. OCR:
//    Python requería instalar Tesseract en el SO (apt install tesseract-ocr).
//    tesseract.js es 100% JavaScript, no requiere instalación del sistema.
//    La precisión es similar, pero el rendimiento puede ser menor en PDFs
//    muy grandes (más lento que el binario nativo de C++).
//
// IMPORTANTE: Este módulo SOLO se ejecuta en el servidor (Node.js).
// Jamás se importa en componentes de React o código del cliente.
// El comentario 'server-only' lo garantiza en Next.js 14.
// ─────────────────────────────────────────────────────────────────────────────

import "server-only";

// ─────────────────────────────────────────────────────────────────────────────
// HELPERS — Equivalentes a _tiene_texto_util() y _limpiar_texto() de Python
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Comprueba que el texto extraído tiene contenido real, no solo espacios/saltos.
 * Python original: def _tiene_texto_util(texto, minimo_caracteres=50)
 *
 * @param texto - Texto a evaluar
 * @param minimoCaracteres - Mínimo de caracteres "reales" (sin espacios)
 */
function tieneTextoUtil(texto: string, minimoCaracteres = 50): boolean {
  if (!texto) return false;
  // Eliminar todos los espacios en blanco y comprobar longitud mínima
  const limpio = texto.replace(/[\s\n\r\t]+/g, "");
  return limpio.length >= minimoCaracteres;
}

/**
 * Elimina líneas completamente vacías repetidas y espacios sobrantes.
 * Python original: def _limpiar_texto(texto)
 *
 * TRADUCCIÓN DIRECTA:
 *   Python: re.sub(r"\n{3,}", "\n\n", texto)
 *   TypeScript: texto.replace(/\n{3,}/g, "\n\n")
 *
 *   Python: [l.rstrip() for l in texto.splitlines()]
 *   TypeScript: texto.split("\n").map(l => l.trimEnd())
 */
function limpiarTexto(texto: string): string {
  if (!texto) return "";
  // Normalizar más de 2 saltos de línea consecutivos
  let resultado = texto.replace(/\n{3,}/g, "\n\n");
  // Eliminar espacios al final de cada línea
  resultado = resultado
    .split("\n")
    .map((l) => l.trimEnd())
    .join("\n")
    .trim();
  return resultado;
}

// ─────────────────────────────────────────────────────────────────────────────
// ESTRATEGIA 1: pdf-parse (equivalente a pdfplumber + pypdf de Python)
//
// Python: pdfplumber abría página a página con layout=False, luego layout=True
// Node.js: pdf-parse extrae todo el texto en una sola llamada con opciones
//          de tolerancia similares. No tiene extracción de tablas nativa como
//          pdfplumber, pero sí detecta separadores de columna mediante espacios.
//
// VENTAJA sobre Python: No requiere instalar librerías del sistema.
// ─────────────────────────────────────────────────────────────────────────────
async function extraerConPdfParse(buffer: Buffer): Promise<string> {
  // Importación dinámica para que Next.js no lo incluya en el bundle del cliente
  const pdfParse = (await import("pdf-parse")).default;

  const datos = await pdfParse(buffer, {
    // pagerender: función personalizada para marcar separaciones de página
    // Equivale al marcador "--- PAGINA N ---" de pdfplumber en Python
    pagerender: (pageData: { pageIndex: number; getTextContent: () => Promise<{ items: Array<{ str: string; transform: number[] }> }> }) => {
      return pageData.getTextContent().then((textContent) => {
        let textoUltimo = "";
        let y = 0;
        let texto = `\n\n--- PAGINA ${pageData.pageIndex + 1} ---\n`;

        for (const item of textContent.items) {
          // Detectar salto de línea por cambio en coordenada Y
          if (textoUltimo !== "" && y !== item.transform[5]) {
            texto += "\n";
          }
          texto += item.str;
          textoUltimo = item.str;
          y = item.transform[5];
        }
        return texto;
      });
    },
  });

  return datos.text.trim();
}

// ─────────────────────────────────────────────────────────────────────────────
// ESTRATEGIA 2: pdf-parse modo simple (fallback, equivalente a pypdf en Python)
//
// Si la estrategia 1 falla por error de renderizado personalizado, intentamos
// la extracción básica sin pagerender personalizado.
// ─────────────────────────────────────────────────────────────────────────────
async function extraerConPdfParseSimple(buffer: Buffer): Promise<string> {
  const pdfParse = (await import("pdf-parse")).default;
  // Sin opciones extra — equivalente al extract_text() básico de pypdf
  const datos = await pdfParse(buffer);
  return datos.text.trim();
}

// ─────────────────────────────────────────────────────────────────────────────
// ESTRATEGIA 3: OCR con tesseract.js
//
// Python original: pytesseract + pdf2image (requería binarios del SO)
// Node.js: tesseract.js (100% JavaScript, sin dependencias del sistema)
//
// DIFERENCIA IMPORTANTE:
//   Python convertía el PDF a imágenes PNG con pdf2image (que usa poppler),
//   luego aplicaba OCR a cada imagen.
//   tesseract.js puede procesar imágenes directamente pero no PDFs.
//   Para PDFs escaneados, la estrategia es:
//   1. Intentar extraer texto con pdf-parse (a veces funciona mínimamente)
//   2. Si no hay texto, aplicar OCR sobre el buffer raw (limitado)
//
// NOTA: Para producción con muchos PDFs escaneados, considera añadir
// 'pdf-to-img' o 'canvas' + 'pdfjs-dist' para rasterizar páginas antes del OCR.
// ─────────────────────────────────────────────────────────────────────────────
async function extraerConOCR(buffer: Buffer): Promise<string> {
  const Tesseract = await import("tesseract.js");

  // tesseract.js trabaja con ArrayBuffer, Uint8Array o rutas de imagen
  // Para PDFs necesitamos primero intentar obtener el buffer como imagen
  // Nota: OCR directo sobre PDF funciona para PDFs de una página escaneada
  const { data } = await Tesseract.recognize(
    buffer,
    "spa", // Español — equivale al lang="spa" de pytesseract en Python
    {
      // Silenciar logs de tesseract.js en producción
      logger: process.env.NODE_ENV === "development"
        ? (m: { status: string; progress: number }) => {
            if (m.status === "recognizing text") {
              process.stdout.write(`\rOCR progreso: ${Math.round(m.progress * 100)}%`);
            }
          }
        : undefined,
    }
  );

  return `\n\n--- PAGINA 1 (OCR) ---\n${data.text}`.trim();
}

// ─────────────────────────────────────────────────────────────────────────────
// FUNCIÓN PRINCIPAL — extraerTexto()
//
// Python original: def extraer_texto(ruta_pdf)
//
// DIFERENCIA PRINCIPAL:
//   Python recibía una ruta del sistema de ficheros (str).
//   TypeScript recibe un Buffer (los bytes del PDF en memoria).
//   Esto es más seguro porque nunca escribe el PDF a disco.
//
// El patrón de fallback es idéntico al Python:
//   Estrategia 1 → Estrategia 2 → Estrategia 3 (OCR)
//   Si ninguna funciona, lanza un Error descriptivo.
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Extrae texto de un PDF usando múltiples estrategias en cascada.
 * Equivalente a extraer_texto(ruta_pdf) de pdf_manager.py
 *
 * @param buffer - Buffer con los bytes del PDF (desde el upload del navegador)
 * @param nombreArchivo - Nombre del archivo (solo para mensajes de error)
 * @returns Texto limpio extraído del PDF
 * @throws Error si ninguna estrategia obtiene texto útil
 */
export async function extraerTexto(
  buffer: Buffer,
  nombreArchivo: string = "archivo.pdf"
): Promise<string> {
  const errores: string[] = [];

  // ── Estrategia 1: pdf-parse con renderizado personalizado ──────────────────
  try {
    const texto = await extraerConPdfParse(buffer);
    if (tieneTextoUtil(texto)) {
      console.log(`[PDF] Estrategia 1 (pdf-parse avanzado) exitosa: ${texto.length} chars`);
      return limpiarTexto(texto);
    }
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    errores.push(`pdf-parse avanzado: ${msg}`);
    console.warn(`[PDF] Estrategia 1 falló: ${msg}`);
  }

  // ── Estrategia 2: pdf-parse simple (fallback) ──────────────────────────────
  try {
    const texto = await extraerConPdfParseSimple(buffer);
    if (tieneTextoUtil(texto)) {
      console.log(`[PDF] Estrategia 2 (pdf-parse simple) exitosa: ${texto.length} chars`);
      return limpiarTexto(texto);
    }
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    errores.push(`pdf-parse simple: ${msg}`);
    console.warn(`[PDF] Estrategia 2 falló: ${msg}`);
  }

  // ── Estrategia 3: OCR con tesseract.js ────────────────────────────────────
  try {
    const texto = await extraerConOCR(buffer);
    if (tieneTextoUtil(texto, 20)) {
      console.log(`[PDF] Estrategia 3 (OCR) exitosa: ${texto.length} chars`);
      return limpiarTexto(texto);
    } else {
      errores.push("OCR: texto extraído insuficiente (¿PDF en blanco o protegido?)");
    }
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    errores.push(`OCR: ${msg}`);
    console.warn(`[PDF] Estrategia 3 (OCR) falló: ${msg}`);
  }

  // Si llegamos aquí, ninguna estrategia funcionó
  const detalle = errores.join(" | ");
  throw new Error(
    `No se pudo extraer texto del PDF "${nombreArchivo}" tras intentar todas las estrategias. ` +
      `Detalle: ${detalle}`
  );
}
