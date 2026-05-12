import { EventEmitter } from "events";

declare global {
  // eslint-disable-next-line no-var
  var __sseEmitter: EventEmitter | undefined;
}

if (!globalThis.__sseEmitter) {
  globalThis.__sseEmitter = new EventEmitter();
  globalThis.__sseEmitter.setMaxListeners(100);
}

export async function GET(
  _request: Request,
  { params }: { params: { sessionId: string } }
): Promise<Response> {
  const { sessionId } = params;

  const stream = new ReadableStream({
    start(controller) {
      const encoder = new TextEncoder();

      controller.enqueue(
        encoder.encode(`data: {"tipo":"conexion","mensaje":"Conexión SSE establecida"}\n\n`)
      );

      const onLog = (mensaje: string) => {
        const payload = JSON.stringify({ tipo: "log", mensaje });
        controller.enqueue(encoder.encode(`data: ${payload}\n\n`));
      };

      const onFin = () => {
        const payload = JSON.stringify({ tipo: "fin" });
        controller.enqueue(encoder.encode(`data: ${payload}\n\n`));
        globalThis.__sseEmitter?.removeListener(sessionId, onLog);
        globalThis.__sseEmitter?.removeListener(`${sessionId}:fin`, onFin);
        controller.close();
      };

      globalThis.__sseEmitter!.on(sessionId, onLog);
      globalThis.__sseEmitter!.once(`${sessionId}:fin`, onFin);

      const heartbeat = setInterval(() => {
        try {
          controller.enqueue(encoder.encode(": heartbeat\n\n"));
        } catch {
          clearInterval(heartbeat);
        }
      }, 15_000);

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
      "Access-Control-Allow-Origin": "*",
    },
  });
}
