// apps/web/src/lib/text-filter.ts
// ─────────────────────────────────────────────────────────────────────────────
// MOTOR DE FILTRADO Y PUNTUACIÓN DE TEXTO
//
// TRADUCCIÓN COMPLETA DE: gui.py (secciones de filtrado, líneas 51-341)
//
// FUNCIONES MIGRADAS:
//   dividir_texto()            → dividirTexto()
//   normalizar_texto()         → normalizarTexto()
//   linea_importante()         → lineaImportante()
//   construir_texto_relevante() → construirTextoRelevante()
//   puntuar_bloque()           → puntuarBloque()
//   seleccionar_bloques_importantes() → seleccionarBloquesImportantes()
//
// DIFERENCIAS DE PARADIGMA (Python → TypeScript):
//
// 1. REGEX:
//    Python usa re.sub(), re.search() del módulo re.
//    TypeScript usa los literales RegExp nativos: /patron/flags
//    Todas las regex de Python se han transcrito directamente.
//
// 2. NORMALIZACIÓN DE UNICODE:
//    Python: unicodedata.normalize("NFKD", texto).encode("ascii", "ignore")
//    TypeScript: texto.normalize("NFD").replace(/[\u0300-\u036f]/g, "")
//    Ambos eliminan tildes/acentos para comparar palabras clave sin acento.
//
// 3. INMUTABILIDAD:
//    Python modificaba listas con .append() directamente.
//    TypeScript usa map/filter/reduce para mantener la inmutabilidad funcional,
//    aunque en funciones de rendimiento se usa push() con arrays locales.
//
// RENDIMIENTO:
//    Este módulo procesa strings de 60.000+ caracteres.
//    TODA la lógica es síncrona y se ejecuta EXCLUSIVAMENTE en el servidor.
//    Nunca se importa en componentes React. El comentario 'server-only' lo
//    garantiza en tiempo de compilación de Next.js.
// ─────────────────────────────────────────────────────────────────────────────

import "server-only";

// ─────────────────────────────────────────────────────────────────────────────
// CONFIGURACIÓN — Equivalente a las constantes globales de gui.py
// ─────────────────────────────────────────────────────────────────────────────

/** Tamaño de cada bloque de texto enviado a Claude (en caracteres) */
export const TAMANO_BLOQUE = 15_000;

/** Solapamiento entre bloques consecutivos para no partir datos en el corte */
export const SOLAPE_BLOQUE = 1_500;

/** Máximo de bloques que se envían a Claude en total */
export const MAX_BLOQUES_CLAUDE = 8;

/** Segundos de espera entre llamadas a Claude para evitar rate limiting */
export const ESPERA_ENTRE_BLOQUES_MS = 10_000; // 10 segundos (en ms para setTimeout)

/** Segundos de espera al recibir error 429 de Anthropic */
export const ESPERA_SI_HAY_LIMITE_MS = 65_000; // 65 segundos

/** Intentos máximos por bloque antes de descartarlo */
export const MAX_INTENTOS_CLAUDE = 2;

/** Primeras N líneas que siempre se incluyen (cabecera del documento) */
export const MAX_LINEAS_INICIALES = 400;

/** Límite total de caracteres del texto filtrado enviado a Claude */
export const MAX_CARACTERES_TEXTO_RELEVANTE = 60_000;

// ─────────────────────────────────────────────────────────────────────────────
// PALABRAS CLAVE Y REGEX — Idénticas a linea_importante() de Python (gui.py)
// ─────────────────────────────────────────────────────────────────────────────

/** Palabras clave normalizadas (sin acentos) que indican línea relevante */
const PALABRAS_CLAVE_FILTRO: string[] = [
  "poliza", "no de poliza", "numero de poliza", "certificado", "suplemento",
  "tomador", "asegurado", "aseguradora", "compania", "mediador", "agente",
  "vehiculo", "matricula", "marca", "modelo", "version", "bastidor", "taxi",
  "conductor", "nif", "dni", "cif", "domicilio", "direccion", "codigo postal",
  "telefono", "email", "correo", "fecha de efecto", "efecto", "vencimiento",
  "fecha de vencimiento", "fecha de emision", "fecha de nacimiento",
  "prima", "recibo", "importe", "total", "iban", "domiciliacion",
  "forma de pago", "garantia", "garantias", "cobertura", "coberturas",
  "responsabilidad civil", "defensa juridica", "asistencia", "lunas",
  "robo", "incendio", "franquicia", "capital", "limite",
  "condiciones particulares", "condiciones especiales", "datos del riesgo",
  "datos bancarios", "prima neta", "impuestos", "consorcio", "bonificacion",
];

/**
 * Patrones regex para detectar matrículas, DNI, IBAN, fechas e importes.
 * Python original: re.compile() estáticos en linea_importante()
 * TypeScript: RegExp literales (el motor JS los compila igual de eficientemente)
 */
const PATRONES_REGEX: RegExp[] = [
  /\b\d{4}\s?[A-Z]{3}\b/,                          // Matrícula nueva: 1234 ABC
  /\b[A-Z]{1,2}\s?\d{4}\s?[A-Z]{1,2}\b/,           // Matrícula vieja: A 1234 BC
  /\b\d{8}[A-Z]\b/,                                 // DNI: 12345678A
  /\b[A-Z]\d{8}\b/,                                 // NIE: X12345678
  /\bES\d{2}\s?\d{4}\s?\d{4}\s?\d{2}\s?\d{10}\b/i, // IBAN español
  /\b\d{1,2}\/\d{1,2}\/\d{2,4}\b/,                 // Fecha: 01/01/2024
  /\b\d{1,2}-\d{1,2}-\d{2,4}\b/,                   // Fecha: 01-01-2024
  /\b\d+[,.]\d{2}\s?€\b/,                           // Importe: 1.234,56 €
  /\b\d+[,.]\d{2}\s?eur\b/i,                        // Importe: 1234.56 EUR
  /\b\d{6,}\b/,                                     // Número largo (nº póliza, etc.)
];

/** Pesos para la puntuación de bloques — equivale al dict de puntuar_bloque() en gui.py */
const PESOS_PALABRAS_CLAVE: Record<string, number> = {
  poliza: 15, certificado: 12, suplemento: 8,
  tomador: 14, asegurado: 12, aseguradora: 8, compania: 8,
  mediador: 8, vehiculo: 15, matricula: 18, marca: 8, modelo: 8,
  bastidor: 12, taxi: 20, conductor: 10,
  nif: 10, dni: 10, cif: 10, fecha: 6, efecto: 10, vencimiento: 10,
  prima: 12, recibo: 12, importe: 8, total: 8, iban: 15,
  garantia: 12, garantias: 12, cobertura: 12, coberturas: 12,
  "responsabilidad civil": 18, franquicia: 10, capital: 8,
  asistencia: 8, "condiciones particulares": 20,
};

// ─────────────────────────────────────────────────────────────────────────────
// FUNCIONES DE NORMALIZACIÓN
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Elimina acentos y pasa a minúsculas para comparación sin diacríticos.
 *
 * Python original:
 *   def normalizar_texto(texto):
 *     cambios = {"á": "a", "é": "e", ...}
 *     for original, nuevo in cambios.items():
 *         texto = texto.replace(original, nuevo)
 *
 * TypeScript usa la API nativa de Unicode (normalize NFD + regex de combining chars)
 * que es más robusta y cubre todos los idiomas, no solo los cambios manuales de Python.
 *
 * NFD descompone "á" en "a" + combining accent (U+0301).
 * La regex /[\u0300-\u036f]/g elimina todos los combining accents.
 */
export function normalizarTexto(texto: string): string {
  return texto
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, ""); // Elimina diacríticos (acentos, ñ→n, ü→u, etc.)
}

// ─────────────────────────────────────────────────────────────────────────────
// DIVISIÓN DE TEXTO EN BLOQUES
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Divide el texto en bloques de tamaño fijo con solapamiento.
 *
 * Python original (gui.py, línea 51):
 *   def dividir_texto(texto, tamano=TAMANO_BLOQUE, solape=SOLAPE_BLOQUE)
 *
 * LÓGICA IDÉNTICA:
 *   - inicio = 0
 *   - fin = min(inicio + tamano, len(texto))
 *   - siguiente inicio = fin - solape (para no perder datos en el corte)
 *
 * El solapamiento asegura que una tabla o cláusula que quede en el borde
 * de dos bloques aparezca completa en al menos uno de ellos.
 */
export function dividirTexto(
  texto: string,
  tamano: number = TAMANO_BLOQUE,
  solape: number = SOLAPE_BLOQUE
): string[] {
  const bloques: string[] = [];
  let inicio = 0;

  while (inicio < texto.length) {
    const fin = Math.min(inicio + tamano, texto.length);
    bloques.push(texto.slice(inicio, fin));

    if (fin >= texto.length) break;

    // El siguiente bloque comienza "solape" caracteres antes del fin del actual
    // para que los datos del borde aparezcan en ambos bloques
    inicio = Math.max(0, fin - solape);
  }

  return bloques;
}

// ─────────────────────────────────────────────────────────────────────────────
// FILTRADO POR RELEVANCIA DE LÍNEAS
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Determina si una línea contiene información relevante de la póliza.
 *
 * Python original (gui.py, línea 118):
 *   def linea_importante(linea)
 *
 * LÓGICA IDÉNTICA:
 *   1. Comprobar palabras clave (normalizadas sin acentos)
 *   2. Comprobar patrones regex (matrículas, DNI, IBAN, fechas, importes)
 *   3. Líneas con "|" son tablas detectadas por pdfplumber → siempre relevantes
 */
export function lineaImportante(linea: string): boolean {
  const lineaNormalizada = normalizarTexto(linea);

  // Verificar palabras clave
  for (const palabra of PALABRAS_CLAVE_FILTRO) {
    if (lineaNormalizada.includes(palabra)) return true;
  }

  // Verificar patrones regex
  for (const patron of PATRONES_REGEX) {
    if (patron.test(linea)) return true;
  }

  // Las líneas con "|" son tablas (detectadas por pdf-parse o marcadores manuales)
  if (linea.includes("|")) return true;

  return false;
}

// ─────────────────────────────────────────────────────────────────────────────
// CONSTRUCCIÓN DEL TEXTO RELEVANTE
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Filtra el texto del PDF para quedarse solo con las líneas relevantes
 * y su contexto, hasta el límite de caracteres configurado.
 *
 * Python original (gui.py, línea 214):
 *   def construir_texto_relevante(texto)
 *
 * ALGORITMO IDÉNTICO:
 *   1. Si el texto ya es ≤ MAX_CARACTERES, devolverlo limpio sin filtrar
 *   2. Siempre incluir las primeras MAX_LINEAS_INICIALES líneas (cabecera)
 *   3. Para cada línea importante, incluir ±5 líneas de contexto
 *   4. Ordenar por posición original y eliminar duplicados
 *   5. Cortar al llegar a MAX_CARACTERES_TEXTO_RELEVANTE
 *
 * La deduplicación (vistos: Set<string>) es funcional, no estructural:
 * dos líneas con el mismo texto se consideran el mismo dato.
 */
export function construirTextoRelevante(texto: string): string {
  // Eliminar líneas vacías y espacios al inicio/fin de cada línea
  const lineas = texto
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l.length > 0);

  const textoCompleto = lineas.join("\n");

  // Si el texto ya cabe en el límite, devolverlo directamente
  if (textoCompleto.length <= MAX_CARACTERES_TEXTO_RELEVANTE) {
    return textoCompleto;
  }

  // Set de posiciones (índices de línea) que se incluirán en el resultado final
  const posiciones = new Set<number>();

  // PASO 1: Incluir siempre las primeras N líneas (cabecera del documento)
  for (let i = 0; i < Math.min(MAX_LINEAS_INICIALES, lineas.length); i++) {
    posiciones.add(i);
  }

  // PASO 2: Añadir líneas importantes y su contexto (±5 líneas)
  for (let i = 0; i < lineas.length; i++) {
    if (lineaImportante(lineas[i]!)) {
      const inicio = Math.max(0, i - 5);
      const fin = Math.min(lineas.length, i + 6);
      for (let j = inicio; j < fin; j++) {
        posiciones.add(j);
      }
    }
  }

  // PASO 3: Ordenar por posición original (para mantener el orden del documento)
  const posicionesOrdenadas = Array.from(posiciones).sort((a, b) => a - b);

  // PASO 4: Construir resultado sin duplicados y respetando el límite de chars
  const resultado: string[] = [];
  const vistos = new Set<string>();
  let caracteres = 0;

  for (const pos of posicionesOrdenadas) {
    const linea = lineas[pos]!;

    // Deduplicación por contenido (idéntico a Python: `if linea in vistos: continue`)
    if (vistos.has(linea)) continue;
    vistos.add(linea);

    if (caracteres + linea.length + 1 > MAX_CARACTERES_TEXTO_RELEVANTE) break;

    resultado.push(linea);
    caracteres += linea.length + 1;
  }

  return resultado.join("\n");
}

// ─────────────────────────────────────────────────────────────────────────────
// PUNTUACIÓN DE BLOQUES
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Calcula la puntuación de relevancia de un bloque de texto.
 * Los bloques con mayor puntuación se enviarán a Claude primero.
 *
 * Python original (gui.py, línea 255):
 *   def puntuar_bloque(bloque, indice)
 *
 * LÓGICA IDÉNTICA:
 *   1. Suma puntos por cada ocurrencia de palabras clave ponderadas
 *   2. Bonus por líneas con "|" (tablas de datos — 5 pts por cada pipe)
 *   3. Bonus extra por posición inicial del documento:
 *      - Bloque 0 (primero): +200 pts — siempre es muy relevante
 *      - Bloque 1:           +100 pts
 *      - Bloque 2:           +50 pts
 */
export function puntuarBloque(bloque: string, indice: number): number {
  const textoNormalizado = normalizarTexto(bloque);
  let puntos = 0;

  // Sumar puntos por cada aparición de cada palabra clave ponderada
  for (const [palabra, peso] of Object.entries(PESOS_PALABRAS_CLAVE)) {
    // Equivalente a texto.count(palabra) de Python
    // En JS no hay count() nativo: usamos split y contamos partes - 1
    const ocurrencias = textoNormalizado.split(palabra).length - 1;
    puntos += ocurrencias * peso;
  }

  // Bonus por tablas detectadas (líneas con "|")
  // Python: puntos += bloque.count("|") * 5
  const pipes = bloque.split("|").length - 1;
  puntos += pipes * 5;

  // Bonus por posición — los primeros bloques suelen tener datos de cabecera
  if (indice === 0) puntos += 200;
  else if (indice === 1) puntos += 100;
  else if (indice === 2) puntos += 50;

  return puntos;
}

// ─────────────────────────────────────────────────────────────────────────────
// SELECCIÓN DE BLOQUES IMPORTANTES
// ─────────────────────────────────────────────────────────────────────────────

/** Resultado de la selección de bloques con sus índices originales */
export interface ResultadoSeleccionBloques {
  bloques: string[];
  /** Índices 1-based (como en Python) de los bloques seleccionados */
  indicesSeleccionados: number[];
}

/**
 * Selecciona los MAX_BLOQUES_CLAUDE bloques más relevantes para enviar a Claude.
 * Si hay menos bloques que el máximo, los devuelve todos.
 *
 * Python original (gui.py, línea 314):
 *   def seleccionar_bloques_importantes(bloques)
 *
 * ALGORITMO IDÉNTICO:
 *   1. Si hay ≤ MAX_BLOQUES bloques, devolver todos (con índices 1-based)
 *   2. Puntuar todos los bloques
 *   3. Ordenar por puntuación descendente, tomar los top MAX_BLOQUES
 *   4. Reordenar los seleccionados por su posición original (para enviarlos
 *      a Claude en el orden correcto del documento)
 */
export function seleccionarBloquesImportantes(
  bloques: string[]
): ResultadoSeleccionBloques {
  // Si caben todos, devolver todos manteniendo orden original
  if (bloques.length <= MAX_BLOQUES_CLAUDE) {
    return {
      bloques,
      indicesSeleccionados: bloques.map((_, i) => i + 1), // índices 1-based como Python
    };
  }

  // Puntuar cada bloque y guardar su índice original
  const puntuados = bloques.map((bloque, indice) => ({
    puntos: puntuarBloque(bloque, indice),
    indice,
    bloque,
  }));

  // Ordenar por puntuación descendente y seleccionar los mejores
  puntuados.sort((a, b) => b.puntos - a.puntos);
  const seleccionados = puntuados.slice(0, MAX_BLOQUES_CLAUDE);

  // Reordenar por posición original del documento (indice ascendente)
  seleccionados.sort((a, b) => a.indice - b.indice);

  return {
    bloques: seleccionados.map((s) => s.bloque),
    indicesSeleccionados: seleccionados.map((s) => s.indice + 1), // 1-based
  };
}
