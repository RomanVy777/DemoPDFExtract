// apps/web/src/lib/claude.ts
// ─────────────────────────────────────────────────────────────────────────────
// CLIENTE DE CLAUDE AI — Motor de Extracción de Pólizas
//
// TRADUCCIÓN COMPLETA DE: claude_client.py
//
// FUNCIONES MIGRADAS:
//   _herramienta_extraccion()   → HERRAMIENTA_EXTRACCION (constante)
//   _obtener_tool_input()       → obtenerToolInput()
//   _llamar_claude()            → llamarClaude()
//   _normalizar()               → normalizarExtraccion()
//   _fusionar_extracciones()    → fusionarExtracciones()
//   procesar_pdf_completo()     → procesarBloque()
//
// DIFERENCIAS DE PARADIGMA (Python → TypeScript):
//
// 1. SDK:
//    Python: from anthropic import Anthropic → cliente.messages.create()
//    TypeScript: import Anthropic from "@anthropic-ai/sdk" → misma API
//    El SDK oficial de TypeScript tiene el mismo contrato que el de Python.
//
// 2. TIPOS:
//    Python: dict, list, str sin tipado estático
//    TypeScript: Interfaces con Zod para validación en runtime.
//    ExtraccionClaude describe exactamente lo que devuelve la herramienta.
//
// 3. ASYNC:
//    Python: funciones síncronas (el SDK de Anthropic en Python bloquea)
//    TypeScript: todo async/await — el SDK JS es nativo async
//
// 4. MANEJO DE ERRORES:
//    Python: try/except con retorno de tupla ("OTRO", {...})
//    TypeScript: try/catch con tipos de retorno explícitos
//
// 5. REINTENTOS CON RATE LIMIT:
//    Python: time.sleep(ESPERA_SI_HAY_LIMITE) en gui.py
//    TypeScript: await sleep(ESPERA_SI_HAY_LIMITE_MS) — mismo concepto,
//    pero usando Promise para no bloquear el event loop de Node.js
// ─────────────────────────────────────────────────────────────────────────────

import "server-only";
import Anthropic from "@anthropic-ai/sdk";
import { z } from "zod";
import { ESPERA_SI_HAY_LIMITE_MS, MAX_INTENTOS_CLAUDE } from "./text-filter";

// ─────────────────────────────────────────────────────────────────────────────
// CONFIGURACIÓN — Equivalente a las variables de entorno de claude_client.py
// ─────────────────────────────────────────────────────────────────────────────

const MODELO_CLAUDE =
  process.env.CLAUDE_MODEL ?? "claude-sonnet-4-20250514";

const MAX_TOKENS_SALIDA = parseInt(
  process.env.CLAUDE_MAX_TOKENS ?? "4000",
  10
);

const MODO_AGRESIVO =
  process.env.CLAUDE_MODO_AGRESIVO?.toLowerCase() === "true";

const MAX_CARACTERES_ENTRADA = parseInt(
  process.env.CLAUDE_MAX_CARACTERES_ENTRADA ?? "15000",
  10
);

// ─────────────────────────────────────────────────────────────────────────────
// TIPOS Y VALIDACIÓN CON ZOD
//
// Python usaba dict sin tipado. Zod nos da validación en runtime + tipos TS.
// ExtraccionClaude es el contrato exacto de lo que devuelve la herramienta.
// ─────────────────────────────────────────────────────────────────────────────

/** Schema Zod para validar la respuesta de Claude (equivale al input_schema de Python) */
const ExtraccionClaudeSchema = z.object({
  tipo_seguro: z.string().default("OTRO"),
  descripcion: z.string().default("Documento procesado por Claude"),
  // Las tablas son un objeto con valores que pueden ser listas u objetos
  // Python: "tablas": {"tipo": "object"} — sin validación de contenido interior
  tablas: z.record(z.unknown()).default({}),
});

export type ExtraccionClaude = z.infer<typeof ExtraccionClaudeSchema>;

/** Tipos de seguro válidos — idénticos a los del prompt de Python */
export const TIPOS_SEGURO = [
  "AUTO", "HOGAR", "VIDA", "SALUD", "DECESOS",
  "COMERCIO", "COMUNIDAD", "RESPONSABILIDAD_CIVIL", "OTRO",
] as const;

export type TipoSeguro = (typeof TIPOS_SEGURO)[number];

// ─────────────────────────────────────────────────────────────────────────────
// SINGLETON DEL CLIENTE DE ANTHROPIC
//
// Python: _get_cliente() creaba una instancia en cada llamada.
// TypeScript: creamos una sola instancia y la reutilizamos.
// El SDK de Node.js es thread-safe (o más bien, event-loop-safe).
// ─────────────────────────────────────────────────────────────────────────────

function getCliente(): Anthropic {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    throw new Error(
      "No se encontró ANTHROPIC_API_KEY en las variables de entorno."
    );
  }
  return new Anthropic({ apiKey });
}

// ─────────────────────────────────────────────────────────────────────────────
// DEFINICIÓN DE LA HERRAMIENTA (TOOL USE)
//
// Python original (claude_client.py, línea 32):
//   def _herramienta_extraccion(): return [{...}]
//
// TypeScript: constante tipada con el tipo del SDK.
// Tool Use fuerza a Claude a devolver JSON estructurado en lugar de texto libre.
// Equivalente al JSON Schema definido en Python, copiado aquí exactamente.
// ─────────────────────────────────────────────────────────────────────────────

const HERRAMIENTA_EXTRACCION: Anthropic.Tool = {
  name: "registrar_extraccion_seguro",
  description:
    "Registra una extracción estructurada de un documento de seguros para crear tablas dinámicas en MySQL.",
  input_schema: {
    type: "object",
    properties: {
      tipo_seguro: {
        type: "string",
        description: "Tipo de seguro detectado",
      },
      descripcion: {
        type: "string",
        description: "Descripción breve del documento",
      },
      tablas: {
        type: "object",
        description: "Tablas dinámicas detectadas en el documento",
      },
    },
    required: ["tipo_seguro", "descripcion", "tablas"],
  },
};

// ─────────────────────────────────────────────────────────────────────────────
// HELPERS INTERNOS
// ─────────────────────────────────────────────────────────────────────────────

/** Pausa asíncrona — equivale al time.sleep() de Python pero no bloquea Node.js */
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Recorta el texto de entrada al máximo configurado.
 * Python original: def _recortar_texto(texto)
 */
function recortarTexto(texto: string): string {
  if (!texto) return "";
  return String(texto).slice(0, MAX_CARACTERES_ENTRADA);
}

/**
 * Extrae el input de la herramienta de la respuesta de Claude.
 * Python original: def _obtener_tool_input(respuesta)
 *
 * LÓGICA IDÉNTICA:
 *   1. Buscar bloque de tipo "tool_use" con name "registrar_extraccion_seguro"
 *   2. Si no hay tool_use, buscar JSON en el texto de respuesta (fallback)
 *   3. Si no hay nada, lanzar error
 */
function obtenerToolInput(respuesta: Anthropic.Message): unknown {
  // PASO 1: Buscar bloque tool_use — el camino feliz
  for (const bloque of respuesta.content) {
    if (
      bloque.type === "tool_use" &&
      bloque.name === "registrar_extraccion_seguro"
    ) {
      return bloque.input;
    }
  }

  // PASO 2: Fallback — buscar JSON en el texto de respuesta
  // Esto ocurre cuando Claude ignora el tool_choice (muy raro pero posible)
  let textoCompleto = "";
  for (const bloque of respuesta.content) {
    if (bloque.type === "text") {
      textoCompleto += bloque.text;
    }
  }

  if (textoCompleto.trim()) {
    return extraerJsonDesdeTexto(textoCompleto);
  }

  throw new Error("Claude no devolvió datos estructurados.");
}

/**
 * Extrae JSON desde texto libre (fallback si Tool Use falla).
 * Python original: def _extraer_json_desde_texto(texto)
 */
function extraerJsonDesdeTexto(texto: string): unknown {
  let limpio = texto.trim();

  // Eliminar bloques de código markdown
  if (limpio.startsWith("```json")) limpio = limpio.replace("```json", "").trim();
  if (limpio.startsWith("```")) limpio = limpio.replace("```", "").trim();
  if (limpio.endsWith("```")) limpio = limpio.slice(0, -3).trim();

  // Encontrar el JSON entre las llaves más externas
  const inicio = limpio.indexOf("{");
  const fin = limpio.lastIndexOf("}");

  if (inicio === -1 || fin === -1) {
    throw new Error("Claude no devolvió JSON válido.");
  }

  return JSON.parse(limpio.slice(inicio, fin + 1));
}

// ─────────────────────────────────────────────────────────────────────────────
// PROMPTS — Equivalentes a _prompt_extraccion() y _prompt_auditoria() de Python
// ─────────────────────────────────────────────────────────────────────────────

function promptExtraccion(textoApoyo: string): string {
  const texto = recortarTexto(textoApoyo);
  return `
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
{
  "tipo_seguro": "AUTO | HOGAR | VIDA | SALUD | DECESOS | COMERCIO | COMUNIDAD | RESPONSABILIDAD_CIVIL | OTRO",
  "descripcion": "descripción breve",
  "tablas": {
    "documento": {},
    "poliza": {},
    "tomador": {},
    "asegurado": {},
    "garantias": [],
    "coberturas": [],
    "campos_detectados": [],
    "NUEVA_TABLA_DINAMICA": []
  }
}

IMPORTANTE:
- Puedes crear los nombres de tablas dinámicas que necesites si ves datos que no encajan en las de arriba (ej: franquicias, conductores, inmuebles, etc.).
- La tabla campos_detectados debe incluir pares etiqueta/valor encontrados en el texto que no sepas clasificar.

Texto del fragmento:
"""
${texto}
"""
`.trim();
}

function promptAuditoria(
  textoApoyo: string,
  datosPrimeraPasada: ExtraccionClaude
): string {
  const texto = recortarTexto(textoApoyo);
  const datosStr = JSON.stringify(datosPrimeraPasada, null, 2).slice(0, 6000);
  return `
Eres un auditor de extracción de datos de seguros.

Ya existe una primera extracción. Revisa el mismo fragmento y añade campos que falten.

No elimines datos anteriores.
No inventes datos.
Devuelve de nuevo el JSON completo usando la herramienta registrar_extraccion_seguro.

Extracción anterior:
${datosStr}

Texto del fragmento:
"""
${texto}
"""
`.trim();
}

// ─────────────────────────────────────────────────────────────────────────────
// LLAMADA A CLAUDE CON REINTENTOS
//
// Python: _llamar_claude() en claude_client.py + lógica de retry en gui.py
// TypeScript: Todo en una sola función async con retry interno
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Llama a Claude con Tool Use y reintentos automáticos por rate limit.
 *
 * DIFERENCIA CON PYTHON:
 *   En Python, el retry estaba repartido entre _llamar_claude() y
 *   el bucle de gui.py (_procesar_bloques_con_claude).
 *   Aquí centralizamos el retry en esta función, con callbacks de log
 *   para que la UI pueda mostrar el progreso en tiempo real.
 *
 * @param prompt - Prompt de usuario para Claude
 * @param onLog - Callback para emitir mensajes de progreso (sustituye a _log_seguro)
 */
async function llamarClaude(
  prompt: string,
  onLog?: (msg: string) => void
): Promise<ExtraccionClaude> {
  const cliente = getCliente();

  for (let intento = 1; intento <= MAX_INTENTOS_CLAUDE; intento++) {
    try {
      const respuesta = await cliente.messages.create({
        model: MODELO_CLAUDE,
        max_tokens: MAX_TOKENS_SALIDA,
        temperature: 0, // 0 = máxima determinismo, igual que en Python
        tools: [HERRAMIENTA_EXTRACCION],
        tool_choice: {
          type: "tool",
          name: "registrar_extraccion_seguro",
        },
        messages: [{ role: "user", content: prompt }],
      });

      const input = obtenerToolInput(respuesta);

      // Validar con Zod — Python no tenía validación de schema en runtime
      const resultado = ExtraccionClaudeSchema.safeParse(input);
      if (!resultado.success) {
        throw new Error(`Claude devolvió estructura inválida: ${resultado.error.message}`);
      }

      return resultado.data;
    } catch (error) {
      const mensaje = error instanceof Error ? error.message : String(error);
      const esRateLimit =
        mensaje.includes("rate_limit_error") ||
        mensaje.includes("429") ||
        mensaje.includes("rate limit");

      if (esRateLimit && intento < MAX_INTENTOS_CLAUDE) {
        onLog?.(
          `Rate limit de Claude alcanzado (intento ${intento}/${MAX_INTENTOS_CLAUDE}). ` +
            `Esperando ${ESPERA_SI_HAY_LIMITE_MS / 1000}s...`
        );
        await sleep(ESPERA_SI_HAY_LIMITE_MS);
        continue; // Reintentar
      }

      // Error no recuperable o último intento: relanzar
      throw error;
    }
  }

  // Este punto es inalcanzable, pero TypeScript necesita el return
  throw new Error("Máximo de intentos agotado.");
}

// ─────────────────────────────────────────────────────────────────────────────
// NORMALIZACIÓN Y FUSIÓN DE RESULTADOS
//
// TRADUCCIÓN DIRECTA de las funciones de claude_client.py:
//   _normalizar()              → normalizarExtraccion()
//   _valor_vacio()             → esValorVacio()
//   _clave_fila()              → claveFilaDuplicados()
//   _fusionar_listas()         → fusionarListas()
//   _fusionar_diccionarios()   → fusionarDiccionarios()
//   _fusionar_extracciones()   → fusionarExtracciones()
// ─────────────────────────────────────────────────────────────────────────────

function normalizarExtraccion(datos: unknown): ExtraccionClaude {
  if (typeof datos !== "object" || datos === null) {
    return { tipo_seguro: "OTRO", descripcion: "Respuesta no válida", tablas: {} };
  }

  const parsed = ExtraccionClaudeSchema.safeParse(datos);
  if (!parsed.success) {
    return { tipo_seguro: "OTRO", descripcion: "Respuesta no válida", tablas: {} };
  }

  const resultado = parsed.data;
  resultado.tipo_seguro = String(resultado.tipo_seguro).toUpperCase() || "OTRO";
  return resultado;
}

function esValorVacio(valor: unknown): boolean {
  return (
    valor === null ||
    valor === undefined ||
    valor === "" ||
    (Array.isArray(valor) && valor.length === 0) ||
    (typeof valor === "object" && !Array.isArray(valor) && Object.keys(valor as object).length === 0)
  );
}

/** Genera una clave única para detectar filas duplicadas en listas */
function claveFilaDuplicados(fila: unknown): string {
  if (typeof fila !== "object" || fila === null) return String(fila);
  const partes: string[] = [];
  for (const clave of Object.keys(fila as Record<string, unknown>).sort()) {
    const valor = (fila as Record<string, unknown>)[clave];
    if (!esValorVacio(valor)) {
      partes.push(`${clave}:${valor}`);
    }
  }
  return partes.join("|");
}

function fusionarListas(lista1: unknown[], lista2: unknown[]): unknown[] {
  const resultado: unknown[] = [];
  const vistos = new Set<string>();

  for (const fila of [...lista1, ...lista2]) {
    const clave = claveFilaDuplicados(fila);
    if (!vistos.has(clave)) {
      resultado.push(fila);
      vistos.add(clave);
    }
  }
  return resultado;
}

function fusionarDiccionarios(
  dic1: Record<string, unknown>,
  dic2: Record<string, unknown>
): Record<string, unknown> {
  const resultado = { ...dic1 };

  for (const [clave, valor2] of Object.entries(dic2)) {
    const valor1 = resultado[clave];

    if (esValorVacio(valor1) && !esValorVacio(valor2)) {
      resultado[clave] = valor2;
    } else if (
      typeof valor1 === "object" && !Array.isArray(valor1) && valor1 !== null &&
      typeof valor2 === "object" && !Array.isArray(valor2) && valor2 !== null
    ) {
      resultado[clave] = fusionarDiccionarios(
        valor1 as Record<string, unknown>,
        valor2 as Record<string, unknown>
      );
    } else if (Array.isArray(valor1) && Array.isArray(valor2)) {
      resultado[clave] = fusionarListas(valor1, valor2);
    } else if (!(clave in resultado)) {
      resultado[clave] = valor2;
    }
  }
  return resultado;
}

/**
 * Fusiona dos extracciones de Claude en una sola sin perder datos.
 * Python original: def _fusionar_extracciones(datos_1, datos_2)
 */
export function fusionarExtracciones(
  datos1: ExtraccionClaude,
  datos2: ExtraccionClaude
): ExtraccionClaude {
  const d1 = normalizarExtraccion(datos1);
  const d2 = normalizarExtraccion(datos2);

  // Si d1 ya tiene tipo concreto, se preserva; si no, se usa el de d2
  const tipoFinal =
    d1.tipo_seguro !== "OTRO" ? d1.tipo_seguro : d2.tipo_seguro;

  const tablas1 = d1.tablas;
  const tablas2 = d2.tablas;
  const nombresTablas = new Set([...Object.keys(tablas1), ...Object.keys(tablas2)]);

  const tablasResultado: Record<string, unknown> = {};

  for (const nombreTabla of nombresTablas) {
    const v1 = tablas1[nombreTabla];
    const v2 = tablas2[nombreTabla];

    if (Array.isArray(v1) || Array.isArray(v2)) {
      const l1 = Array.isArray(v1) ? v1 : v1 ? [v1] : [];
      const l2 = Array.isArray(v2) ? v2 : v2 ? [v2] : [];
      tablasResultado[nombreTabla] = fusionarListas(l1, l2);
    } else if (
      typeof v1 === "object" && v1 !== null &&
      typeof v2 === "object" && v2 !== null
    ) {
      tablasResultado[nombreTabla] = fusionarDiccionarios(
        v1 as Record<string, unknown>,
        v2 as Record<string, unknown>
      );
    } else {
      tablasResultado[nombreTabla] = !esValorVacio(v1) ? v1 : v2;
    }
  }

  return {
    tipo_seguro: tipoFinal,
    descripcion: d1.descripcion || d2.descripcion || "Documento procesado por Claude",
    tablas: tablasResultado,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// FUNCIÓN PRINCIPAL DE PROCESAMIENTO DE UN BLOQUE
//
// Python original: def procesar_pdf_completo(texto, ruta_pdf)
//
// DIFERENCIAS:
//   Python devolvía una tupla: (tipo_seguro, datos_completos)
//   TypeScript devuelve un objeto tipado: { tipo, datos }
//   El tipo se extrae del objeto para evitar la ambigüedad de las tuplas.
// ─────────────────────────────────────────────────────────────────────────────

export interface ResultadoProcesamiento {
  tipo: string;
  datos: ExtraccionClaude;
}

/**
 * Procesa un bloque de texto con Claude y devuelve la extracción estructurada.
 * Equivalente a procesar_pdf_completo() de claude_client.py
 *
 * @param texto - Fragmento de texto a procesar
 * @param onLog - Callback para emitir logs de progreso en tiempo real
 */
export async function procesarBloque(
  texto: string,
  onLog?: (msg: string) => void
): Promise<ResultadoProcesamiento> {
  try {
    if (!texto || texto.trim() === "") {
      return {
        tipo: "OTRO",
        datos: { tipo_seguro: "OTRO", descripcion: "Bloque vacío", tablas: {} },
      };
    }

    // Primera pasada — extracción principal
    const prompt1 = promptExtraccion(texto);
    const datos1 = normalizarExtraccion(await llamarClaude(prompt1, onLog));

    let datosFinal = datos1;

    // Segunda pasada de auditoría (solo en MODO_AGRESIVO)
    // Equivalente al bloque `if MODO_AGRESIVO:` de Python
    if (MODO_AGRESIVO) {
      onLog?.("Modo agresivo: ejecutando auditoría de segunda pasada...");
      const prompt2 = promptAuditoria(texto, datos1);
      const datos2 = normalizarExtraccion(await llamarClaude(prompt2, onLog));
      datosFinal = fusionarExtracciones(datos1, datos2);
    }

    const tipo = String(datosFinal.tipo_seguro || "OTRO").toUpperCase();
    datosFinal.tipo_seguro = tipo;

    return { tipo, datos: datosFinal };
  } catch (error) {
    const mensaje = error instanceof Error ? error.message : String(error);
    return {
      tipo: "OTRO",
      datos: {
        tipo_seguro: "OTRO",
        descripcion: "Error procesando el bloque con Claude",
        tablas: {},
        // Campo extra para debugging — no va a la BD
        ...(process.env.NODE_ENV === "development" ? { _error: mensaje } : {}),
      },
    };
  }
}
