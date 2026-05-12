# Claude PDF Extractor — Monorepo Enterprise

Migración completa de la aplicación Python/Tkinter a arquitectura web Enterprise con Next.js 14, tRPC, Prisma y MySQL.

---

## Arquitectura

```
seguros-monorepo/
├── apps/
│   └── web/                          # Aplicación Next.js 14
│       ├── prisma/
│       │   └── schema.prisma         # Tablas fijas (documentos, tablas_generadas, errores)
│       └── src/
│           ├── app/
│           │   ├── api/
│           │   │   ├── trpc/[trpc]/  # Handler HTTP de tRPC
│           │   │   └── sse/[sessionId]/ # Server-Sent Events (logs en tiempo real)
│           │   ├── layout.tsx
│           │   └── page.tsx          # UI: Drag & Drop + Consola de logs
│           ├── lib/
│           │   ├── prisma.ts         # Singleton de Prisma Client
│           │   ├── pdf-extractor.ts  # Motor PDF (≡ pdf_manager.py)
│           │   ├── text-filter.ts    # Filtrado y puntuación (≡ gui.py lógica)
│           │   ├── claude.ts         # Cliente Claude AI (≡ claude_client.py)
│           │   ├── database.ts       # Gestor BD (≡ database_manager.py)
│           │   └── trpc/
│           │       ├── client.ts     # Cliente tRPC para el browser
│           │       └── provider.tsx  # React Provider
│           └── server/
│               ├── trpc.ts           # Configuración base tRPC
│               └── routers/
│                   ├── app.router.ts # Router raíz
│                   └── pdf.router.ts # Procedimientos de PDF (≡ importar_pdf)
└── turbo.json                        # Configuración Turborepo
```

---

## Tabla de Equivalencias Python → TypeScript

| Python (original)              | TypeScript (migrado)                        |
|-------------------------------|---------------------------------------------|
| `pdf_manager.py`              | `src/lib/pdf-extractor.ts`                  |
| `gui.py` (filtrado)           | `src/lib/text-filter.ts`                    |
| `claude_client.py`            | `src/lib/claude.ts`                         |
| `database_manager.py`         | `src/lib/database.ts`                       |
| `gui.py` (AppDemo / Tkinter)  | `src/app/page.tsx` (React)                  |
| `mysql.connector.connect()`   | Prisma Client + `$executeRawUnsafe`         |
| `threading.Thread`            | `async/await` nativo                        |
| `self._log_seguro()`          | Server-Sent Events (`/api/sse/[sessionId]`) |
| `time.sleep()`                | `await sleep(ms)` (no bloquea event loop)   |
| `pdfplumber` / `pypdf`        | `pdf-parse`                                 |
| `pytesseract`                 | `tesseract.js`                              |
| Flask / sin framework web     | Next.js 14 App Router + tRPC                |

---

## Instalación

### 1. Prerrequisitos

- Node.js ≥ 20.0.0
- MySQL 8.x corriendo localmente (o Docker)
- npm ≥ 10.0.0

### 2. Clonar y configurar variables de entorno

```bash
# Clonar el repositorio
git clone <repo> seguros-monorepo
cd seguros-monorepo

# Copiar variables de entorno
cp .env.example .env

# Editar .env con tus credenciales
nano .env
```

Variables mínimas requeridas en `.env`:
```env
DATABASE_URL="mysql://root:password@localhost:3306/seguros_demo"
ANTHROPIC_API_KEY="sk-ant-api03-..."
CLAUDE_MODEL="claude-sonnet-4-20250514"
```

### 3. Instalar dependencias

```bash
npm install
```

### 4. Inicializar la base de datos

```bash
# Generar el Prisma Client
cd apps/web
npx prisma generate

# Crear tablas fijas en MySQL (documentos, tablas_generadas, errores_importacion)
npx prisma db push

# (Opcional) Abrir Prisma Studio para inspeccionar la BD
npx prisma studio
```

### 5. Arrancar en desarrollo

```bash
# Desde la raíz del monorepo
npm run dev
```

La aplicación estará en: http://localhost:3000

---

## Flujo de Procesamiento

El flujo es idéntico al original de Python, ahora async:

```
1. [Browser] Usuario arrastra PDF → se convierte a base64
2. [tRPC]    procesarPdf.mutate({ pdfBase64, nombreArchivo, sessionId })
3. [SSE]     Browser abre EventSource /api/sse/{sessionId} para recibir logs
4. [Server]  extraerTexto(buffer)          ← pdf-extractor.ts (estrategias en cascada)
5. [Server]  construirTextoRelevante(texto) ← text-filter.ts (filtrado por palabras clave)
6. [Server]  dividirTexto(relevante)       ← bloques de 15.000 chars con 1.500 solape
7. [Server]  seleccionarBloquesImportantes() ← puntuación y selección top-8
8. [Server]  Para cada bloque → procesarBloque(texto) ← claude.ts (Tool Use)
9. [Server]  fusionarExtracciones()        ← resultado acumulado sin duplicados
10.[Server]  guardarDocumento()            ← Prisma (tabla documentos)
11.[Server]  crearTablasDesdeClaude()     ← Raw SQL dinámico en MySQL
12.[Browser] Mostrar resumen con tablas creadas
```

---

## Seguridad SQL (Verificación)

| Amenaza                         | Mitigación                                          |
|--------------------------------|-----------------------------------------------------|
| SQL Injection en nombres tabla  | `escaparIdentificadorMySQL()` — backticks + escape  |
| SQL Injection en valores        | Parámetros `?` en `$executeRawUnsafe(..., ...vals)` |
| Nombres inválidos de columna    | `normalizarNombre()` — solo `[a-z0-9_]`             |
| Desbordamiento LONGTEXT         | `limpiarValor()` — todos los valores como string    |
| Palabras reservadas MySQL       | `PALABRAS_RESERVADAS_MYSQL` — prefijo automático    |

### Verificación de dialectos MySQL ✅

```sql
-- ✅ AUTO_INCREMENT (no IDENTITY de SQL Server)
CREATE TABLE IF NOT EXISTS tabla (
  id INT AUTO_INCREMENT PRIMARY KEY,
  ...
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ✅ LONGTEXT (no TEXT ni VARCHAR para campos largos)
ALTER TABLE `tabla_dinamica` ADD COLUMN `campo` LONGTEXT;

-- ✅ SHOW COLUMNS (dialecto MySQL para introspección)
SHOW COLUMNS FROM `tabla_dinamica`;

-- ✅ ON DELETE CASCADE en FOREIGN KEY
FOREIGN KEY (id_documento) REFERENCES documentos(id) ON DELETE CASCADE
```

---

## Variables de Entorno

| Variable                        | Defecto                       | Descripción                              |
|--------------------------------|-------------------------------|------------------------------------------|
| `DATABASE_URL`                 | —                             | URL de conexión MySQL para Prisma        |
| `ANTHROPIC_API_KEY`            | —                             | API key de Anthropic (obligatoria)       |
| `CLAUDE_MODEL`                 | `claude-sonnet-4-20250514`    | Modelo de Claude a usar                  |
| `CLAUDE_MAX_TOKENS`            | `4000`                        | Tokens máximos de respuesta              |
| `CLAUDE_MODO_AGRESIVO`         | `false`                       | Segunda pasada de auditoría por bloque   |
| `CLAUDE_MAX_CARACTERES_ENTRADA`| `15000`                       | Máx. chars por bloque enviado a Claude   |

---

## Escalabilidad y Producción

Para despliegue con múltiples instancias (PM2 cluster, Kubernetes):

1. **SSE con EventEmitter local** no funciona entre procesos distintos.
   Sustituir `globalThis.__sseEmitter` por **Redis Pub/Sub**:
   ```typescript
   import { createClient } from "redis";
   const redis = createClient({ url: process.env.REDIS_URL });
   await redis.publish(sessionId, mensaje);
   ```

2. **Pool de conexiones MySQL**: Prisma gestiona el pool automáticamente.
   Configura `connection_limit` en `DATABASE_URL`:
   ```
   DATABASE_URL="mysql://...?connection_limit=10"
   ```

3. **PDFs grandes**: Para archivos >50MB, usar `multipart/form-data`
   en lugar de base64 via tRPC (que tiene límite de body).
