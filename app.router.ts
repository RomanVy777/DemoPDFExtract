// apps/web/src/server/routers/app.router.ts
// Router raíz que combina todos los sub-routers del monorepo

import { router } from "../trpc";
import { pdfRouter } from "./pdf.router";

/**
 * Router raíz de la aplicación.
 * Equivale al app de Flask/FastAPI en Python que registraba blueprints.
 *
 * Para añadir nuevos dominios: importar el router y añadirlo aquí.
 */
export const appRouter = router({
  pdf: pdfRouter,
});

// Tipo exportado para que el cliente tRPC esté completamente tipado
export type AppRouter = typeof appRouter;
