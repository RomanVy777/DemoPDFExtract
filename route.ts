// apps/web/src/app/api/trpc/[trpc]/route.ts
// ─────────────────────────────────────────────────────────────────────────────
// HANDLER HTTP PARA tRPC — App Router de Next.js 14
//
// Este fichero expone el endpoint HTTP que acepta las llamadas tRPC.
// En Python/Flask sería: @app.route("/api/trpc/<path>", methods=["GET", "POST"])
//
// Next.js App Router usa fetch handlers en lugar de Express-style middleware.
// fetchRequestHandler adapta las Request/Response de Web API al formato tRPC.
// ─────────────────────────────────────────────────────────────────────────────

import { fetchRequestHandler } from "@trpc/server/adapters/fetch";
import { appRouter } from "@/server/routers/app.router";
import { createTRPCContext } from "@/server/trpc";

const handler = (req: Request) =>
  fetchRequestHandler({
    endpoint: "/api/trpc",
    req,
    router: appRouter,
    createContext: createTRPCContext,
    onError:
      process.env.NODE_ENV === "development"
        ? ({ path, error }) => {
            console.error(`[tRPC] Error en /${path ?? "<ruta desconocida>"}:`, error);
          }
        : undefined,
  });

export { handler as GET, handler as POST };
