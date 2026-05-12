// apps/web/src/server/trpc.ts
// ─────────────────────────────────────────────────────────────────────────────
// CONFIGURACIÓN BASE DE tRPC
//
// tRPC es el equivalente moderno a definir endpoints REST manualmente.
// En Python/Flask haríamos @app.route("/api/procesar-pdf", methods=["POST"]).
// Con tRPC, el cliente TypeScript llama a funciones del servidor de forma
// completamente tipada sin escribir fetch(), headers, ni parsear JSON.
//
// COMPONENTES:
//   - initTRPC: Inicializa el framework con SuperJSON (serialización avanzada)
//   - publicProcedure: Equivale a un endpoint abierto (sin autenticación)
//   - Context: Datos disponibles en todos los procedimientos (DB, sesión, etc.)
// ─────────────────────────────────────────────────────────────────────────────

import { initTRPC } from "@trpc/server";
import superjson from "superjson";
import { ZodError } from "zod";
import { prisma } from "@/lib/prisma";

/**
 * Context de tRPC — disponible en todos los procedimientos.
 * Equivale a los parámetros que pasaríamos en cada función de Python.
 */
export async function createTRPCContext() {
  return {
    prisma,
  };
}

export type Context = Awaited<ReturnType<typeof createTRPCContext>>;

const t = initTRPC.context<Context>().create({
  // SuperJSON permite serializar tipos que JSON.stringify no soporta:
  // Date, BigInt, Map, Set, undefined, etc.
  transformer: superjson,

  // Formatear errores de validación Zod de forma legible
  errorFormatter({ shape, error }) {
    return {
      ...shape,
      data: {
        ...shape.data,
        zodError:
          error.cause instanceof ZodError ? error.cause.flatten() : null,
      },
    };
  },
});

// Exportar helpers tipados
export const router = t.router;
export const publicProcedure = t.procedure;
export const createCallerFactory = t.createCallerFactory;
