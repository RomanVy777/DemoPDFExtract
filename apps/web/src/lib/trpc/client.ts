// apps/web/src/lib/trpc/client.ts
// ─────────────────────────────────────────────────────────────────────────────
// CLIENTE tRPC PARA EL BROWSER
//
// Este fichero configura el cliente tRPC que usan los componentes React.
// Equivale a la capa que en Python sería el requests.post() o el fetch() manual,
// pero completamente tipado y sin necesidad de escribir la URL, headers, ni parsear JSON.
//
// PATRÓN DE USO EN COMPONENTES REACT:
//   const { mutate } = trpc.pdf.procesarPdf.useMutation()
//   → Esto es EXACTAMENTE como llamar a la función procesarPdf del servidor,
//     con autocompletado de parámetros y tipos de retorno garantizados.
// ─────────────────────────────────────────────────────────────────────────────

import { createTRPCReact } from "@trpc/react-query";
import type { AppRouter } from "@/server/routers/app.router";

/**
 * Cliente tRPC tipado con el AppRouter del servidor.
 * Exportar desde aquí garantiza un único punto de creación (singleton).
 */
export const trpc = createTRPCReact<AppRouter>();
