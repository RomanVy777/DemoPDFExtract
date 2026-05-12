"use client";
// apps/web/src/app/page.tsx
// ─────────────────────────────────────────────────────────────────────────────
// INTERFAZ PRINCIPAL — Equivalente a gui.py (AppDemo class en Tkinter)
//
// COMPONENTES MIGRADOS DESDE PYTHON:
//   drop_label (CTkLabel con DnD)     → <DropZone> con HTML5 Drag & Drop API
//   badge_tipo (CTkLabel)             → <TipoSeguroBadge>
//   btn_procesar (CTkButton)          → <button> con estados
//   progress (CTkProgressBar)         → <ProgressBar> con animación CSS
//   resultado_txt (CTkTextbox)        → <LogConsole> con SSE en tiempo real
//
// DIFERENCIAS DE PARADIGMA (Tkinter → React):
//
// 1. THREADING vs ASYNC:
//    Python: threading.Thread(target=self._logica_pesada).start()
//    React: trpc.pdf.procesarPdf.mutate() — async nativo, no bloquea la UI
//
// 2. ACTUALIZACIÓN DE UI:
//    Python: self.after(0, lambda: widget.configure(text=...)) — thread-safe updates
//    React: setState() — React re-renderiza automáticamente al cambiar estado
//
// 3. LOGS EN TIEMPO REAL:
//    Python: self._log_seguro() → CTkTextbox.insert("end", texto)
//    React: EventSource (SSE) → array de logs en estado de React
//
// 4. DRAG & DROP:
//    Python: TkinterDnD con drop_target_register(DND_FILES)
//    React: HTML5 File Drag & Drop API (nativo, sin librería extra)
//
// 5. PROCESAMIENTO DEL PDF:
//    Python: ruta_pdf = event.data (ruta del filesystem local)
//    React: file.arrayBuffer() → base64 → enviado al servidor via tRPC
// ─────────────────────────────────────────────────────────────────────────────

import { useState, useCallback, useRef, useEffect } from "react";
import { trpc } from "@/lib/trpc/client";
import type { ResultadoProcesarPdf } from "@/server/routers/pdf.router";

// ─────────────────────────────────────────────────────────────────────────────
// TIPOS
// ─────────────────────────────────────────────────────────────────────────────

type EstadoProceso = "idle" | "procesando" | "completado" | "error";

interface LogEntry {
  id: number;
  texto: string;
  ts: Date;
}

// ─────────────────────────────────────────────────────────────────────────────
// CONSTANTES DE ESTILO — Colores por tipo de seguro (equivale a ICONOS_TIPO en Python)
// ─────────────────────────────────────────────────────────────────────────────
const COLORES_TIPO: Record<string, string> = {
  AUTO: "#4f7cff",
  HOGAR: "#43d9ad",
  VIDA: "#ff6b9d",
  SALUD: "#a8ff78",
  DECESOS: "#b8b8ff",
  COMERCIO: "#ffd460",
  COMUNIDAD: "#f093fb",
  RESPONSABILIDAD_CIVIL: "#f5a623",
  OTRO: "#8892b0",
};

// ─────────────────────────────────────────────────────────────────────────────
// COMPONENTE: DropZone
//
// Equivale al drop_label de Tkinter + el binding dnd_bind("<<Drop>>")
// Usa la API nativa de HTML5 para arrastrar ficheros.
// ─────────────────────────────────────────────────────────────────────────────
interface DropZoneProps {
  onArchivo: (file: File) => void;
  archivoCargado: string | null;
  disabled: boolean;
}

function DropZone({ onArchivo, archivoCargado, disabled }: DropZoneProps) {
  const [arrastrandoEncima, setArrastrandoEncima] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const manejarArchivo = useCallback(
    (file: File) => {
      if (!file.name.toLowerCase().endsWith(".pdf")) {
        alert("Solo se permiten archivos PDF.");
        return;
      }
      onArchivo(file);
    },
    [onArchivo]
  );

  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    if (!disabled) setArrastrandoEncima(true);
  };

  const onDragLeave = () => setArrastrandoEncima(false);

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setArrastrandoEncima(false);
    if (disabled) return;
    const file = e.dataTransfer.files[0];
    if (file) manejarArchivo(file);
  };

  const onClick = () => {
    if (!disabled) inputRef.current?.click();
  };

  const onInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) manejarArchivo(file);
  };

  const colorBorde = arrastrandoEncima
    ? "#4f7cff"
    : archivoCargado
    ? "#43d9ad"
    : "#2e3352";

  return (
    <div
      onClick={onClick}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      style={{
        border: `2px dashed ${colorBorde}`,
        borderRadius: "12px",
        padding: "40px 24px",
        textAlign: "center",
        cursor: disabled ? "not-allowed" : "pointer",
        backgroundColor: arrastrandoEncima ? "rgba(79, 124, 255, 0.08)" : "#1a1d27",
        transition: "all 0.2s ease",
        opacity: disabled ? 0.6 : 1,
        userSelect: "none",
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".pdf"
        style={{ display: "none" }}
        onChange={onInputChange}
      />

      {/* Icono PDF */}
      <div style={{ fontSize: "48px", marginBottom: "12px" }}>
        {archivoCargado ? "📄" : "📂"}
      </div>

      {archivoCargado ? (
        <>
          <p style={{ color: "#43d9ad", fontWeight: 600, marginBottom: "4px" }}>
            {archivoCargado}
          </p>
          <p style={{ color: "#8892b0", fontSize: "13px" }}>
            {disabled ? "Procesando..." : "Haz clic o arrastra otro PDF para cambiar"}
          </p>
        </>
      ) : (
        <>
          <p style={{ color: "#e8eaf6", fontWeight: 600, fontSize: "16px", marginBottom: "8px" }}>
            Arrastra tu PDF de póliza aquí
          </p>
          <p style={{ color: "#8892b0", fontSize: "13px" }}>
            o haz clic para seleccionar un archivo
          </p>
        </>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// COMPONENTE: LogConsole
//
// Equivale al CTkTextbox de Tkinter con fuente Courier.
// Muestra los logs en tiempo real recibidos via SSE.
// Se desplaza automáticamente al último mensaje (resultado_txt.see("end"))
// ─────────────────────────────────────────────────────────────────────────────
interface LogConsoleProps {
  logs: LogEntry[];
}

function LogConsole({ logs }: LogConsoleProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll al último log — equivale a resultado_txt.see("end") de Tkinter
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  return (
    <div
      style={{
        backgroundColor: "#0d1117",
        border: "1px solid #2e3352",
        borderRadius: "8px",
        padding: "16px",
        height: "340px",
        overflowY: "auto",
        fontFamily: "'JetBrains Mono', 'Cascadia Code', monospace",
        fontSize: "12px",
        lineHeight: "1.7",
      }}
    >
      {logs.length === 0 ? (
        <span style={{ color: "#8892b0" }}>
          Los logs del proceso aparecerán aquí...
        </span>
      ) : (
        logs.map((log) => (
          <div key={log.id} style={{ color: colorDeLog(log.texto) }}>
            <span style={{ color: "#3d4663", marginRight: "8px" }}>
              {log.ts.toLocaleTimeString("es-ES")}
            </span>
            {log.texto}
          </div>
        ))
      )}
      <div ref={bottomRef} />
    </div>
  );
}

/** Colorea los logs según su contenido — UX mejorada respecto al Tkinter original */
function colorDeLog(texto: string): string {
  if (texto.startsWith("ERROR") || texto.includes("falló") || texto.includes("error"))
    return "#ff6b6b";
  if (texto.includes("correctamente") || texto.includes("✓") || texto.startsWith("PROCESO"))
    return "#43d9ad";
  if (texto.includes("Esperando") || texto.includes("rate limit"))
    return "#ffd460";
  if (texto.startsWith("─") || texto.startsWith("PROCESO"))
    return "#4f7cff";
  return "#cdd6f4";
}

// ─────────────────────────────────────────────────────────────────────────────
// COMPONENTE: TipoSeguroBadge — equivale al badge_tipo de Python
// ─────────────────────────────────────────────────────────────────────────────
function TipoSeguroBadge({ tipo }: { tipo: string }) {
  const color = COLORES_TIPO[tipo] ?? COLORES_TIPO.OTRO!;
  return (
    <div
      style={{
        display: "inline-block",
        backgroundColor: `${color}22`,
        border: `1px solid ${color}`,
        borderRadius: "20px",
        padding: "6px 16px",
        color,
        fontWeight: 700,
        fontSize: "14px",
        letterSpacing: "0.05em",
      }}
    >
      ● Póliza de {tipo} detectada
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// COMPONENTE: ResultadoResumen
// ─────────────────────────────────────────────────────────────────────────────
function ResultadoResumen({ resultado }: { resultado: ResultadoProcesarPdf }) {
  return (
    <div
      style={{
        backgroundColor: "#1a1d27",
        border: "1px solid #2e3352",
        borderRadius: "8px",
        padding: "16px",
        marginTop: "12px",
      }}
    >
      <h3 style={{ color: "#4f7cff", marginBottom: "12px", fontSize: "14px" }}>
        RESUMEN DE IMPORTACIÓN
      </h3>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px", fontSize: "13px" }}>
        <div style={{ color: "#8892b0" }}>ID Documento</div>
        <div style={{ color: "#e8eaf6" }}>#{resultado.idDocumento}</div>

        <div style={{ color: "#8892b0" }}>Tipo de seguro</div>
        <div style={{ color: "#43d9ad", fontWeight: 700 }}>{resultado.tipoSeguro}</div>

        <div style={{ color: "#8892b0" }}>Texto extraído</div>
        <div style={{ color: "#e8eaf6" }}>
          {resultado.textoExtraido.total.toLocaleString("es-ES")} chars
          <span style={{ color: "#8892b0", marginLeft: "6px" }}>
            (reducido {resultado.textoExtraido.reduccion.toFixed(1)}%)
          </span>
        </div>

        <div style={{ color: "#8892b0" }}>Bloques procesados</div>
        <div style={{ color: "#e8eaf6" }}>
          {resultado.bloques.correctos}/{resultado.bloques.enviados} correctos
        </div>

        <div style={{ color: "#8892b0" }}>Tablas creadas</div>
        <div style={{ color: "#e8eaf6" }}>{resultado.tablasCreadas.length}</div>
      </div>

      {resultado.tablasCreadas.length > 0 && (
        <div style={{ marginTop: "12px" }}>
          <div style={{ color: "#8892b0", fontSize: "12px", marginBottom: "6px" }}>
            Tablas en MySQL:
          </div>
          {resultado.tablasCreadas.map((tabla) => (
            <div
              key={tabla}
              style={{
                color: "#43d9ad",
                fontSize: "12px",
                padding: "2px 0",
              }}
            >
              ✓ {tabla}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// PÁGINA PRINCIPAL
// ─────────────────────────────────────────────────────────────────────────────

export default function PaginaPrincipal() {
  const [archivoActual, setArchivoActual] = useState<File | null>(null);
  const [estado, setEstado] = useState<EstadoProceso>("idle");
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [tipoSeguro, setTipoSeguro] = useState<string | null>(null);
  const [resultado, setResultado] = useState<ResultadoProcesarPdf | null>(null);
  const logIdRef = useRef(0);
  const sseRef = useRef<EventSource | null>(null);

  // Añadir un log a la consola
  const addLog = useCallback((texto: string) => {
    setLogs((prev) => [
      ...prev,
      { id: logIdRef.current++, texto, ts: new Date() },
    ]);
  }, []);

  // Limpiar logs
  const clearLogs = () => {
    setLogs([]);
    setTipoSeguro(null);
    setResultado(null);
  };

  const mutation = trpc.pdf.procesarPdf.useMutation({
    onSuccess: (data) => {
      setEstado("completado");
      setTipoSeguro(data.tipoSeguro);
      setResultado(data);
      // Señalizar fin de la sesión SSE
      sseRef.current?.close();
    },
    onError: (error) => {
      setEstado("error");
      addLog(`ERROR: ${error.message}`);
      sseRef.current?.close();
    },
  });

  const procesarPdf = async () => {
    if (!archivoActual) return;

    clearLogs();
    setEstado("procesando");

    // Generar sessionId único para esta sesión SSE
    const sessionId = `${Date.now()}-${Math.random().toString(36).slice(2)}`;

    // Abrir conexión SSE para recibir logs en tiempo real
    const sse = new EventSource(`/api/sse/${sessionId}`);
    sseRef.current = sse;

    sse.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as { tipo: string; mensaje?: string };
        if (payload.tipo === "log" && payload.mensaje) {
          addLog(payload.mensaje);
          // Detectar tipo de seguro en los logs para el badge
          const match = payload.mensaje.match(/Tipo de seguro detectado:\s+(\w+)/);
          if (match?.[1]) setTipoSeguro(match[1]);
        }
      } catch {
        // Ignorar mensajes SSE mal formados
      }
    };

    sse.onerror = () => sse.close();

    // Convertir el File a base64 para enviarlo via tRPC
    const base64 = await new Promise<string>((resolve) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = reader.result as string;
        resolve(result.split(",")[1]!);
      };
      reader.readAsDataURL(archivoActual);
    });

    mutation.mutate({
      pdfBase64: base64,
      nombreArchivo: archivoActual.name,
      sessionId,
    });
  };

  const alSeleccionarArchivo = (file: File) => {
    setArchivoActual(file);
    clearLogs();
    setEstado("idle");
    addLog(`Archivo seleccionado: ${file.name}`);
    addLog(`Tamaño: ${(file.size / 1024).toFixed(1)} KB`);
  };

  const estaProcesando = estado === "procesando";

  return (
    <main
      style={{
        maxWidth: "860px",
        margin: "0 auto",
        padding: "40px 20px",
        minHeight: "100vh",
      }}
    >
      {/* Cabecera */}
      <div style={{ marginBottom: "32px" }}>
        <h1
          style={{
            fontSize: "22px",
            fontWeight: 700,
            color: "#e8eaf6",
            letterSpacing: "-0.02em",
            marginBottom: "6px",
          }}
        >
          <span style={{ color: "#4f7cff" }}>●</span> Claude PDF Extractor
        </h1>
        <p style={{ color: "#8892b0", fontSize: "13px" }}>
          Extrae datos estructurados de pólizas de seguros y los guarda en MySQL
        </p>
      </div>

      {/* Drop Zone */}
      <DropZone
        onArchivo={alSeleccionarArchivo}
        archivoCargado={archivoActual?.name ?? null}
        disabled={estaProcesando}
      />

      {/* Badge tipo seguro */}
      <div style={{ marginTop: "12px", minHeight: "36px", display: "flex", alignItems: "center" }}>
        {tipoSeguro && <TipoSeguroBadge tipo={tipoSeguro} />}
      </div>

      {/* Botón procesar */}
      <button
        onClick={procesarPdf}
        disabled={!archivoActual || estaProcesando}
        style={{
          display: "block",
          width: "100%",
          padding: "14px",
          marginTop: "8px",
          backgroundColor:
            !archivoActual || estaProcesando ? "#1a1d27" : "#4f7cff",
          color:
            !archivoActual || estaProcesando ? "#3d4663" : "#ffffff",
          border: "1px solid",
          borderColor:
            !archivoActual || estaProcesando ? "#2e3352" : "#4f7cff",
          borderRadius: "8px",
          fontSize: "14px",
          fontWeight: 700,
          cursor: !archivoActual || estaProcesando ? "not-allowed" : "pointer",
          transition: "all 0.2s ease",
          letterSpacing: "0.02em",
          fontFamily: "inherit",
        }}
      >
        {estaProcesando
          ? "⏳ Analizando PDF e insertando en MySQL..."
          : "▶ Analizar PDF e insertar en MySQL"}
      </button>

      {/* Barra de progreso indeterminada */}
      {estaProcesando && (
        <div
          style={{
            height: "3px",
            backgroundColor: "#1a1d27",
            borderRadius: "2px",
            overflow: "hidden",
            marginTop: "8px",
          }}
        >
          <div
            style={{
              height: "100%",
              backgroundColor: "#4f7cff",
              animation: "progress-indeterminate 1.5s ease-in-out infinite",
              width: "40%",
            }}
          />
        </div>
      )}

      <style>{`
        @keyframes progress-indeterminate {
          0% { transform: translateX(-200%); }
          100% { transform: translateX(350%); }
        }
      `}</style>

      {/* Consola de logs */}
      <div style={{ marginTop: "16px" }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "8px",
          }}
        >
          <span style={{ color: "#8892b0", fontSize: "12px", fontWeight: 600 }}>
            CONSOLA
          </span>
          {logs.length > 0 && !estaProcesando && (
            <button
              onClick={clearLogs}
              style={{
                background: "none",
                border: "none",
                color: "#3d4663",
                fontSize: "12px",
                cursor: "pointer",
                fontFamily: "inherit",
              }}
            >
              limpiar
            </button>
          )}
        </div>
        <LogConsole logs={logs} />
      </div>

      {/* Resumen final */}
      {resultado && estado === "completado" && (
        <ResultadoResumen resultado={resultado} />
      )}
    </main>
  );
}
