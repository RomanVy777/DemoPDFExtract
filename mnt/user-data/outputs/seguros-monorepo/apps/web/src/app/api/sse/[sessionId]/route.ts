// apps/web/src/app/api/sse/[sessionId]/route.ts
// ─────────────────────────────────────────────────────────────────────────────
// ENDPOINT SERVER-SENT EVENTS (SSE) — Consola de Logs en Tiempo Real
//
// EQUIVALENCIA CON PYTHON:
//   gui.py._log_seguro() → self.after(0, self._log()) enviaba texto al
//   widget CTkTextbox de Tkinter usando el mecanismo de threading de Tk.
//
//   En la web, Server-Sent Events (SSE) es el equivalente moderno:
//   el servidor mantiene una conexión HTTP abierta y envía eventos
//   text/event-stream al navegador a medida que ocurren.
//
// FLUJO:
//   1. El frontend abre una conexión SSE a /api/sse/{sessionId}
//   2. El procedimiento tRPC procesarPdf llama a globalThis.__sseEmitter.emit(sessionId, msg)
//   3. Este endpoint recoge el evento y lo reenvía al navegador
//   4. El frontend muestra el mensaje en la consola de logs
//
// VENTAJA vs WebSockets:
//   SSE es unidireccional (servidor → cliente), más simple de implementar
//   en Next.js que WebSockets, y suficiente para logs de progreso.
// ─────────────────────────────────────────────────────────────────────────────

import { EventEmitter } from "events";

// ─────────────────────────────────────────────────────────────────────────────
// EventEmitter global compartido entre el endpoint SSE y el router tRPC
//
// En Node.js, globalThis persiste entre requests del mismo proceso.
// Esto permite que el procedimiento tRPC emita eventos que este endpoint recoge.
//
// ⚠️  En producción con múltiples instancias (PM2, Kubernetes), usar Redis Pub/Sub
//     en lugar de EventEmitter local.
// ─────────────────────────────────────────────────────────────────────────────

declare global {
  // eslint-disable-next-line no-var
  var __sseEmitter: EventEmitter | undefined;
}

if (!globalThis.__sseEmitter) {
  globalThis.__sseEmitter = new EventEmitter();
  globalThis.__sseEmitter.setMaxListeners(100); // Evitar warnings con muchas sesiones
}

export async function GET(
  _request: Request,
  { params }: { params: { sessionId: string } }
): Promise<Response> {
  const { sessionId } = params;

  // ReadableStream de Web API — compatible con Next.js Edge Runtime y Node.js
  const stream = new ReadableStream({
    start(controller) {
      const encoder = new TextEncoder();

      // Enviar mensaje de conexión establecida
      controller.enqueue(
        encoder.encode(`data: {"tipo":"conexion","mensaje":"Conexión SSE establecida"}\n\n`)
      );

      // Listener que reenvía los mensajes de log al navegador
      const onLog = (mensaje: string) => {
        const payload = JSON.stringify({ tipo: "log", mensaje });
        controller.enqueue(encoder.encode(`data: ${payload}\n\n`));
      };

      // Listener de fin de proceso
      const onFin = () => {
        const payload = JSON.stringify({ tipo: "fin" });
        controller.enqueue(encoder.encode(`data: ${payload}\n\n`));
        globalThis.__sseEmitter?.removeListener(sessionId, onLog);
        globalThis.__sseEmitter?.removeListener(`${sessionId}:fin`, onFin);
        controller.close();
      };

      globalThis.__sseEmitter!.on(sessionId, onLog);
      globalThis.__sseEmitter!.once(`${sessionId}:fin`, onFin);

      // Heartbeat cada 15s para mantener la conexión activa (algunos proxies cierran
      // conexiones inactivas — equivale al trick de Tkinter con after(ms, callback))
      const heartbeat = setInterval(() => {
        try {
          controller.enqueue(encoder.encode(": heartbeat\n\n"));
        } catch {
          clearInterval(heartbeat);
        }
      }, 15_000);

      // Limpieza cuando el cliente cierra la conexión
      return () => {
        clearInterval(heartbeat);
        globalThis.__sseEmitter?.removeListener(sessionId, onLog);
        globalThis.__sseEmitter?.removeListener(`${sessionId}:fin`, onFin);
      };
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      // CORS para desarrollo
      "Access-Control-Allow-Origin": "*",
    },
  });
}
