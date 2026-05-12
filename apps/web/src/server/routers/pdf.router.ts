// apps/web/src/server/routers/pdf.router.ts
// ─────────────────────────────────────────────────────────────────────────────
// ROUTER PRINCIPAL DE PROCESAMIENTO DE PDFs
//
// EQUIVALENCIA CON PYTHON:
//   gui.py._logica_pesada() → procedimiento tRPC procesarPdf
//   gui.py._log_seguro()    → emisión de logs via callback onLog
//
// El flujo de procesamiento es idéntico al de _logica_pesada() de Python:
//   1. Extraer texto del PDF
//   2. Filtrar texto relevante
//   3. Dividir en bloques
//   4. Seleccionar bloques importantes
//   5. Enviar bloques a Claude (con reintentos)
//   6. Guardar documento en MySQL
//   7. Crear tablas dinámicas
//
// CONSOLA DE LOGS EN TIEMPO REAL:
//   Python usaba threading.Thread + self._log_seguro() → self.after(0, self._log())
//   TypeScript usa Server-Sent Events (SSE) para enviar logs al navegador en
//   tiempo real. El endpoint /api/procesar-pdf/stream maneja la conexión SSE.
//   El procedimiento tRPC retorna el resultado final; los logs intermedios
//   van por SSE.
// ─────────────────────────────────────────────────────────────────────────────

import { z } from "zod";
import { router, publicProcedure } from "../trpc";
import { extraerTexto } from "@/lib/pdf-extractor";
import {
  construirTextoRelevante,
  dividirTexto,
  seleccionarBloquesImportantes,
  ESPERA_ENTRE_BLOQUES_MS,
  MAX_INTENTOS_CLAUDE,
} from "@/lib/text-filter";
import { procesarBloque, fusionarExtracciones } from "@/lib/claude";
import type { ExtraccionClaude } from "@/lib/claude";
import {
  guardarDocumento,
  crearTablasDesdeClaude,
  guardarError,
} from "@/lib/database";

// ─────────────────────────────────────────────────────────────────────────────
// HELPER: sleep async (no bloquea el event loop)
// En Python: time.sleep(ESPERA_ENTRE_BLOQUES)
// ─────────────────────────────────────────────────────────────────────────────
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// ─────────────────────────────────────────────────────────────────────────────
// HELPER: Fusionar datos de un bloque en el resultado acumulado
//
// Python original: self._fusionar_jsons(resultado_final, datos_bloque) en gui.py
// TypeScript: función pura que devuelve el resultado fusionado
// ─────────────────────────────────────────────────────────────────────────────
function fusionarEnResultado(
  destino: ExtraccionClaude,
  nuevo: ExtraccionClaude
): ExtraccionClaude {
  return fusionarExtracciones(destino, nuevo);
}

// ─────────────────────────────────────────────────────────────────────────────
// RESULTADO DEL PROCEDIMIENTO
// ─────────────────────────────────────────────────────────────────────────────

const ResultadoProcesarPdfSchema = z.object({
  idDocumento: z.number(),
  tipoSeguro: z.string(),
  tablasCreadas: z.array(z.string()),
  textoExtraido: z.object({
    total: z.number(),
    enviado: z.number(),
    reduccion: z.number(),
  }),
  bloques: z.object({
    generados: z.number(),
    enviados: z.number(),
    correctos: z.number(),
    indices: z.array(z.number()),
  }),
});

export type ResultadoProcesarPdf = z.infer<typeof ResultadoProcesarPdfSchema>;

// ─────────────────────────────────────────────────────────────────────────────
// ROUTER
// ─────────────────────────────────────────────────────────────────────────────

export const pdfRouter = router({
  /**
   * Procedimiento principal: recibe el PDF en base64 y ejecuta el flujo completo.
   *
   * El cliente envía:
   *   - pdfBase64: string (el PDF codificado en base64)
   *   - nombreArchivo: string
   *   - sessionId: string (para identificar la sesión SSE de logs)
   *
   * Python equivalente: importar_pdf() + _logica_pesada()
   *
   * Los logs en tiempo real NO van por tRPC sino por SSE (/api/sse/[sessionId]).
   * El sessionId permite al servidor emitir logs a la sesión correcta del browser.
   */
  procesarPdf: publicProcedure
    .input(
      z.object({
        pdfBase64: z.string().min(1, "El PDF no puede estar vacío"),
        nombreArchivo: z.string().min(1),
        sessionId: z.string().min(1),
      })
    )
    .output(ResultadoProcesarPdfSchema)
    .mutation(async ({ input }) => {
      const { pdfBase64, nombreArchivo, sessionId } = input;

      // Función de log que emite al canal SSE de esta sesión
      const log = (mensaje: string) => {
        // Emitir al EventEmitter global para que el endpoint SSE lo recoja
        globalThis.__sseEmitter?.emit(sessionId, mensaje);
        console.log(`[${sessionId}] ${mensaje}`);
      };

      log(`Iniciando procesamiento de: ${nombreArchivo}`);

      // ── PASO 1: Convertir base64 a Buffer ──────────────────────────────────
      // Python: ruta_pdf era una ruta del sistema de ficheros
      // TypeScript: el PDF llega desde el navegador como base64
      const pdfBuffer = Buffer.from(pdfBase64, "base64");

      // ── PASO 2: Extraer texto del PDF ──────────────────────────────────────
      log("1. Extrayendo texto del PDF...");
      let textoCompleto: string;
      try {
        textoCompleto = await extraerTexto(pdfBuffer, nombreArchivo);
      } catch (error) {
        const msg = error instanceof Error ? error.message : String(error);
        log(`ERROR al extraer texto: ${msg}`);
        await guardarError(null, `Extracción PDF fallida: ${msg}`);
        throw new Error(`No se pudo extraer texto del PDF: ${msg}`);
      }

      if (!textoCompleto.trim()) {
        const msg = "No se ha podido extraer texto del PDF (puede ser escaneado o protegido).";
        log(msg);
        throw new Error(msg);
      }

      log(`Texto extraído: ${textoCompleto.length.toLocaleString("es-ES")} caracteres`);

      // ── PASO 3: Filtrar texto relevante ────────────────────────────────────
      log("2. Filtrando texto relevante del PDF...");
      let textoRelevante = construirTextoRelevante(textoCompleto);

      if (!textoRelevante.trim()) {
        log("No se encontró texto relevante. Usando el inicio del documento.");
        textoRelevante = textoCompleto.slice(0, 60_000);
      }

      const porcentajeEnviado = (textoRelevante.length * 100) / textoCompleto.length;
      const reduccion = 100 - porcentajeEnviado;

      log(`Texto original: ${textoCompleto.length.toLocaleString("es-ES")} chars`);
      log(`Texto enviado a Claude: ${textoRelevante.length.toLocaleString("es-ES")} chars`);
      log(`Reducción aproximada: ${reduccion.toFixed(2)}%`);

      // ── PASO 4: Dividir en bloques ─────────────────────────────────────────
      log("\n3. Dividiendo texto relevante en bloques...");
      const todosBloques = dividirTexto(textoRelevante);
      log(`Bloques generados: ${todosBloques.length}`);

      // ── PASO 5: Seleccionar bloques importantes ────────────────────────────
      log("4. Seleccionando bloques más importantes...");
      const { bloques: bloquesImportantes, indicesSeleccionados } =
        seleccionarBloquesImportantes(todosBloques);

      log(`Bloques que se enviarán a Claude: ${bloquesImportantes.length} de ${todosBloques.length}`);
      log(`Bloques seleccionados: [${indicesSeleccionados.join(", ")}]`);

      // ── PASO 6: Procesar bloques con Claude ────────────────────────────────
      log("\n5. Enviando bloques importantes a Claude...");

      let resultadoFinal: ExtraccionClaude = {
        tipo_seguro: "OTRO",
        descripcion: "Documento procesado por Claude por bloques relevantes",
        tablas: {},
      };

      let bloquesCorrectos = 0;

      for (let i = 0; i < bloquesImportantes.length; i++) {
        const bloque = bloquesImportantes[i]!;
        log(`\nProcesando bloque ${i + 1} de ${bloquesImportantes.length}...`);

        let exito = false;

        for (let intento = 1; intento <= MAX_INTENTOS_CLAUDE; intento++) {
          try {
            const { tipo, datos } = await procesarBloque(bloque, log);

            // Fusionar con el resultado acumulado
            resultadoFinal = fusionarEnResultado(resultadoFinal, datos);

            // Actualizar tipo si lo teníamos como OTRO
            if (resultadoFinal.tipo_seguro === "OTRO" && tipo !== "OTRO") {
              resultadoFinal.tipo_seguro = tipo;
            }

            log(`Bloque ${i + 1}: procesado correctamente (tipo: ${tipo})`);
            bloquesCorrectos++;
            exito = true;
            break;
          } catch (error) {
            const msg = error instanceof Error ? error.message : String(error);
            const esRateLimit =
              msg.includes("429") ||
              msg.includes("rate_limit") ||
              msg.includes("rate limit");

            if (esRateLimit && intento < MAX_INTENTOS_CLAUDE) {
              log(`Bloque ${i + 1}: rate limit (intento ${intento}). Esperando ${ESPERA_ENTRE_BLOQUES_MS / 1000}s...`);
              await sleep(ESPERA_ENTRE_BLOQUES_MS);
            } else {
              log(`Bloque ${i + 1}: error — ${msg}`);
              break;
            }
          }
        }

        if (!exito) {
          log(`Bloque ${i + 1}: descartado por errores.`);
        }

        // Esperar entre bloques para no saturar la API
        if (i < bloquesImportantes.length - 1) {
          log(`Esperando ${ESPERA_ENTRE_BLOQUES_MS / 1000}s antes del siguiente bloque...`);
          await sleep(ESPERA_ENTRE_BLOQUES_MS);
        }
      }

      if (bloquesCorrectos === 0) {
        throw new Error("Claude no pudo procesar ningún bloque correctamente.");
      }

      const tipoFinal = resultadoFinal.tipo_seguro;
      log(`\nTipo de seguro detectado: ${tipoFinal}`);

      // ── PASO 7: Guardar documento en MySQL ─────────────────────────────────
      log("6. Guardando documento principal en MySQL...");
      const idDocumento = await guardarDocumento({
        nombreArchivo,
        tipoSeguro: tipoFinal,
        textoExtraido: textoCompleto,
        datosClaude: resultadoFinal,
      });
      log(`Documento guardado con ID: ${idDocumento}`);

      // ── PASO 8: Crear tablas dinámicas ─────────────────────────────────────
      log("7. Creando tablas dinámicas en MySQL...");
      const { tablasCreadas } = await crearTablasDesdeClaude(
        idDocumento,
        resultadoFinal
      );

      log(`Tablas creadas/actualizadas: ${tablasCreadas.length}`);
      for (const tabla of tablasCreadas) {
        log(`  ✓ ${tabla}`);
      }

      log("\n" + "─".repeat(50));
      log("PROCESO COMPLETADO CORRECTAMENTE");
      log("─".repeat(50));

      return {
        idDocumento,
        tipoSeguro: tipoFinal,
        tablasCreadas,
        textoExtraido: {
          total: textoCompleto.length,
          enviado: textoRelevante.length,
          reduccion: Math.round(reduccion * 100) / 100,
        },
        bloques: {
          generados: todosBloques.length,
          enviados: bloquesImportantes.length,
          correctos: bloquesCorrectos,
          indices: indicesSeleccionados,
        },
      };
    }),

  /**
   * Obtiene la lista de documentos procesados.
   * Útil para mostrar historial en la UI.
   */
  listarDocumentos: publicProcedure.query(async ({ ctx }) => {
    return ctx.prisma.documento.findMany({
      orderBy: { fecha_importacion: "desc" },
      take: 50,
      select: {
        id: true,
        nombre_archivo: true,
        tipo_seguro: true,
        fecha_importacion: true,
        _count: { select: { tablas_generadas: true } },
      },
    });
  }),
});
