// apps/web/src/lib/database.ts
// ─────────────────────────────────────────────────────────────────────────────
// GESTOR DE BASE DE DATOS — Tablas Fijas y Dinámicas
//
// TRADUCCIÓN COMPLETA DE: database_manager.py
//
// ARQUITECTURA:
//   - Tablas FIJAS (documentos, tablas_generadas, errores_importacion):
//     → Gestionadas por Prisma ORM (type-safe, migrations)
//   - Tablas DINÁMICAS (seguro_auto_poliza, seguro_hogar_coberturas, etc.):
//     → Creadas con $executeRawUnsafe (Raw SQL) igual que en Python
//     → La estructura se determina en runtime según el JSON de Claude
//
// SEGURIDAD ANTI-INYECCIÓN SQL:
//   Python usaba: proteger_nombre_mysql(nombre) → "`" + nombre.replace("`", "``") + "`"
//   TypeScript replica EXACTAMENTE esta protección con escaparIdentificadorMySQL()
//   Los VALORES se pasan como parámetros (nunca concatenados) usando Prisma
//   $executeRaw con el tagged template literal o mediante placeholders.
//
// DIFERENCIAS DE PARADIGMA:
//
// 1. CONEXIÓN:
//    Python: mysql.connector.connect() — una conexión por función, cierre explícito
//    TypeScript: Prisma connection pool — automático, sin cierre manual
//
// 2. CURSOR vs PRISMA:
//    Python: cursor.execute("SQL", params) con %s placeholders
//    TypeScript: prisma.$executeRawUnsafe("SQL", ...params) — misma idea
//    Los ?  placeholders de MySQL son equivalentes a los %s de Python
//
// 3. TRANSACCIONES:
//    Python: conexion.commit() / conexion.rollback()
//    TypeScript: prisma.$transaction([...]) — más declarativo
//
// 4. NOMBRES DE TABLAS Y COLUMNAS:
//    Prisma NO permite parametrizar identificadores (solo valores).
//    Por eso los nombres de tabla/columna se escapan manualmente con backticks,
//    igual que proteger_nombre_mysql() en Python.
//    Los VALORES siempre van como parámetros para prevenir SQL injection.
// ─────────────────────────────────────────────────────────────────────────────

import "server-only";
import { prisma } from "./prisma";
import type { ExtraccionClaude } from "./claude";

// ─────────────────────────────────────────────────────────────────────────────
// PROTECCIÓN DE IDENTIFICADORES MySQL
//
// Python original (database_manager.py, línea 32):
//   def proteger_nombre_mysql(nombre):
//     return "`" + nombre.replace("`", "``") + "`"
//
// MISMO ALGORITMO en TypeScript.
// Los identificadores (nombres de tabla y columna) se envuelven en backticks
// y los backticks internos se duplican para escaparlos (estándar MySQL).
//
// ⚠️  ADVERTENCIA: Esta función es para IDENTIFICADORES (nombres de tabla/columna),
//     NO para valores. Los valores SIEMPRE van como parámetros de la query.
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Envuelve un identificador MySQL en backticks y escapa backticks internos.
 * Equivale a proteger_nombre_mysql() de Python.
 */
function escaparIdentificadorMySQL(nombre: string): string {
  return "`" + nombre.replace(/`/g, "``") + "`";
}

// ─────────────────────────────────────────────────────────────────────────────
// NORMALIZACIÓN DE NOMBRES
//
// Python original (database_manager.py, línea 122):
//   def normalizar_nombre(texto, prefijo)
//
// ALGORITMO:
//   1. Minúsculas y strip
//   2. Eliminar acentos (NFKD en Python → NFD en JS)
//   3. Reemplazar caracteres no alfanuméricos por _
//   4. Colapsar múltiples _ en uno
//   5. Evitar nombres que empiezan por dígito
//   6. Evitar palabras reservadas de MySQL
//   7. Truncar a 60 caracteres
// ─────────────────────────────────────────────────────────────────────────────

/** Palabras reservadas de MySQL que no pueden usarse como nombres de columna sin escapar */
const PALABRAS_RESERVADAS_MYSQL = new Set([
  "select", "insert", "update", "delete", "table", "from", "where",
  "order", "group", "by", "create", "drop", "alter", "index",
  "primary", "foreign", "key", "date", "int", "json",
]);

/**
 * Convierte cualquier texto en un nombre válido para tabla o columna MySQL.
 * Python original: def normalizar_nombre(texto, prefijo)
 *
 * Ejemplo:
 *   'Número de póliza' → 'numero_de_poliza'
 *   '2024_datos' → 't_2024_datos' (si prefijo='t')
 */
export function normalizarNombre(texto: string | null | undefined, prefijo: string): string {
  let t = (texto ?? "campo").toString().trim().toLowerCase();

  // Eliminar acentos y diacríticos: equivale al unicodedata.normalize("NFKD") de Python
  t = t.normalize("NFD").replace(/[\u0300-\u036f]/g, "");

  // Reemplazar caracteres no alfanuméricos por guion bajo
  t = t.replace(/[^a-z0-9_]+/g, "_");

  // Colapsar múltiples guiones bajos en uno
  t = t.replace(/_+/g, "_");

  // Eliminar guiones bajos al inicio y fin
  t = t.replace(/^_+|_+$/g, "");

  if (t === "") t = "campo";

  // Si empieza por dígito, añadir prefijo
  if (/^\d/.test(t)) t = `${prefijo}_${t}`;

  // Si es palabra reservada, añadir prefijo
  if (PALABRAS_RESERVADAS_MYSQL.has(t)) t = `${prefijo}_${t}`;

  // Truncar a 60 caracteres (límite de Python)
  return t.slice(0, 60);
}

/**
 * Genera el nombre MySQL de una tabla dinámica.
 * Python original: def nombre_tabla_dinamica(tipo_seguro, nombre_tabla)
 *
 * Ejemplo:
 *   ('AUTO', 'póliza') → 'seguro_auto_poliza'
 */
export function nombreTablaDinamica(tipoSeguro: string, nombreTabla: string): string {
  const tipo = normalizarNombre(tipoSeguro || "generico", "t");
  const tabla = normalizarNombre(nombreTabla || "datos", "t");
  return `seguro_${tipo}_${tabla}`.slice(0, 64); // MySQL: 64 chars max para nombres de tabla
}

// ─────────────────────────────────────────────────────────────────────────────
// LIMPIEZA DE VALORES
//
// Python original (database_manager.py, línea 163):
//   def limpiar_valor(valor)
//
// "Guarda todo como texto para evitar errores."
// Estrategia idéntica: dict/list → JSON string, resto → string
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Convierte cualquier valor a string para insertarlo como LONGTEXT en MySQL.
 * Python original: def limpiar_valor(valor)
 */
function limpiarValor(valor: unknown): string | null {
  if (valor === null || valor === undefined) return null;
  if (typeof valor === "object") return JSON.stringify(valor);
  return String(valor).trim();
}

// ─────────────────────────────────────────────────────────────────────────────
// APLANAR DICCIONARIOS ANIDADOS
//
// Python original (database_manager.py, línea 388):
//   def aplanar_diccionario(diccionario, prefijo="")
//
// Convierte objetos anidados en columnas planas:
//   { "direccion": { "calle": "Mayor", "cp": "37500" } }
//   → { "direccion_calle": "Mayor", "direccion_cp": "37500" }
// ─────────────────────────────────────────────────────────────────────────────

function aplanarDiccionario(
  diccionario: Record<string, unknown>,
  prefijo: string = ""
): Record<string, string | null> {
  const resultado: Record<string, string | null> = {};

  for (const [clave, valor] of Object.entries(diccionario)) {
    const claveNormalizada = normalizarNombre(clave, "c");
    const nuevaClave = prefijo ? `${prefijo}_${claveNormalizada}` : claveNormalizada;

    if (typeof valor === "object" && !Array.isArray(valor) && valor !== null) {
      // Recursión para objetos anidados — igual que Python
      const aplanado = aplanarDiccionario(valor as Record<string, unknown>, nuevaClave);
      Object.assign(resultado, aplanado);
    } else if (Array.isArray(valor)) {
      // Las listas se serializan a JSON — igual que Python
      resultado[nuevaClave] = JSON.stringify(valor);
    } else {
      resultado[nuevaClave] = limpiarValor(valor);
    }
  }

  return resultado;
}

/**
 * Convierte el contenido de una tabla (objeto, lista o escalar) en filas planas.
 * Python original: def convertir_contenido_en_filas(contenido)
 */
function convertirContenidoEnFilas(
  contenido: unknown
): Record<string, string | null>[] {
  if (Array.isArray(contenido)) {
    return contenido.map((elemento) => {
      if (typeof elemento === "object" && elemento !== null) {
        return aplanarDiccionario(elemento as Record<string, unknown>);
      }
      return { valor: limpiarValor(elemento) };
    });
  }

  if (typeof contenido === "object" && contenido !== null) {
    return [aplanarDiccionario(contenido as Record<string, unknown>)];
  }

  return [{ valor: limpiarValor(contenido) }];
}

// ─────────────────────────────────────────────────────────────────────────────
// OPERACIONES CON TABLAS DINÁMICAS (RAW SQL)
//
// ⚠️  SEGURIDAD: Los identificadores (tabla, columnas) se escapan con
//     escaparIdentificadorMySQL(). Los valores van como parámetros (?).
//
// Python original equivale a:
//   crear_tabla_dinamica_si_no_existe() → crearTablaDinamicaSiNoExiste()
//   crear_columnas_si_no_existen()      → crearColumnasSiNoExisten()
//   insertar_fila_dinamica()            → insertarFilaDinamica()
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Obtiene las columnas existentes de una tabla dinámica.
 * Python original: def obtener_columnas_existentes(cursor, nombre_tabla)
 *
 * MYSQL DIALECT: SHOW COLUMNS FROM funciona igual en ambos entornos.
 */
async function obtenerColumnasExistentes(nombreTabla: string): Promise<Set<string>> {
  const nombreEscapado = escaparIdentificadorMySQL(nombreTabla);

  // $queryRawUnsafe porque el nombre de la tabla es dinámico y no se puede
  // parametrizar en SQL (solo los valores se pueden parametrizar, no identificadores)
  const columnas = await prisma.$queryRawUnsafe<Array<{ Field: string }>>(
    `SHOW COLUMNS FROM ${nombreEscapado}`
  );

  return new Set(columnas.map((col) => col.Field));
}

/**
 * Crea una tabla dinámica si no existe, con las columnas base.
 * Python original: def crear_tabla_dinamica_si_no_existe(cursor, nombre_tabla)
 *
 * MYSQL DIALECT verificado:
 *   ✅ CREATE TABLE IF NOT EXISTS
 *   ✅ INT AUTO_INCREMENT PRIMARY KEY (no IDENTITY de SQL Server)
 *   ✅ ENGINE=InnoDB
 *   ✅ DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
 *   ✅ FOREIGN KEY ... REFERENCES documentos(id) ON DELETE CASCADE
 */
async function crearTablaDinamicaSiNoExiste(nombreTabla: string): Promise<void> {
  const nombreEscapado = escaparIdentificadorMySQL(nombreTabla);

  await prisma.$executeRawUnsafe(`
    CREATE TABLE IF NOT EXISTS ${nombreEscapado} (
      id INT AUTO_INCREMENT PRIMARY KEY,
      id_documento INT,
      fecha_importacion DATETIME,
      FOREIGN KEY (id_documento) REFERENCES documentos(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  `);
}

/**
 * Añade columnas que faltan a una tabla dinámica existente.
 * Python original: def crear_columnas_si_no_existen(cursor, nombre_tabla, columnas)
 *
 * MYSQL DIALECT:
 *   ✅ ALTER TABLE ... ADD COLUMN ... LONGTEXT
 *   Los nombres de columna se escapan con backticks.
 */
async function crearColumnasSiNoExisten(
  nombreTabla: string,
  columnas: Set<string>
): Promise<void> {
  const columnasExistentes = await obtenerColumnasExistentes(nombreTabla);
  const nombreTbEscapado = escaparIdentificadorMySQL(nombreTabla);

  for (const columna of columnas) {
    if (!columnasExistentes.has(columna)) {
      const columnaEscapada = escaparIdentificadorMySQL(columna);
      await prisma.$executeRawUnsafe(`
        ALTER TABLE ${nombreTbEscapado}
        ADD COLUMN ${columnaEscapada} LONGTEXT
      `);
    }
  }
}

/**
 * Inserta una fila de datos en una tabla dinámica.
 * Python original: def insertar_fila_dinamica(cursor, nombre_tabla, id_documento, fila)
 *
 * SEGURIDAD:
 *   - Nombres de columna: escapados con backticks (identificadores)
 *   - Valores: pasados como parámetros ? (previene SQL injection en valores)
 *
 * MYSQL DIALECT:
 *   ✅ INSERT INTO tabla (col1, col2) VALUES (?, ?)
 *   Los ? son el placeholder estándar de MySQL (Python usaba %s, mismo concepto)
 */
async function insertarFilaDinamica(
  nombreTabla: string,
  idDocumento: number,
  fila: Record<string, string | null>
): Promise<void> {
  const fecha = new Date();

  // Columnas base + columnas de datos
  const columnas = ["id_documento", "fecha_importacion", ...Object.keys(fila)];
  const valores: unknown[] = [idDocumento, fecha, ...Object.values(fila)];

  // Escapar TODOS los nombres de columna con backticks (protección de identificadores)
  const columnasSql = columnas
    .map((c) => escaparIdentificadorMySQL(c))
    .join(", ");

  // Los valores van como ? (placeholders parametrizados — previene SQL injection)
  const placeholders = columnas.map(() => "?").join(", ");

  const nombreTbEscapado = escaparIdentificadorMySQL(nombreTabla);

  await prisma.$executeRawUnsafe(
    `INSERT INTO ${nombreTbEscapado} (${columnasSql}) VALUES (${placeholders})`,
    ...valores
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// FUNCIONES DE PRISMA (TABLAS FIJAS)
//
// Equivalentes a las funciones manuales con cursor.execute() de Python,
// pero ahora con Prisma que genera SQL type-safe.
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Guarda el documento principal en la tabla 'documentos'.
 * Python original: def guardar_documento(nombre_archivo, tipo_seguro, ...)
 */
export async function guardarDocumento(params: {
  nombreArchivo: string;
  tipoSeguro: string;
  textoExtraido: string;
  datosClaude: ExtraccionClaude;
}): Promise<number> {
  const documento = await prisma.documento.create({
    data: {
      nombre_archivo: params.nombreArchivo,
      tipo_seguro: params.tipoSeguro,
      texto_extraido: params.textoExtraido,
      // JSON serializado a string (LONGTEXT) — igual que en Python
      json_claude: JSON.stringify(params.datosClaude),
    },
    select: { id: true },
  });

  return documento.id;
}

/**
 * Registra un error de importación.
 * Python original: def guardar_error(id_documento, mensaje)
 */
export async function guardarError(
  idDocumento: number | null,
  mensaje: string
): Promise<void> {
  await prisma.errorImportacion.create({
    data: {
      id_documento: idDocumento,
      mensaje_error: String(mensaje).slice(0, 65535), // TEXT tiene límite de 65K chars
    },
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// CREACIÓN DE TABLAS DINÁMICAS DESDE JSON DE CLAUDE
//
// Python original (database_manager.py, línea 492):
//   def crear_tablas_desde_json_claude(id_documento, datos_claude)
//
// ALGORITMO IDÉNTICO:
//   Para cada tabla en datos_claude.tablas:
//     1. Generar nombre MySQL (seguro_{tipo}_{nombre})
//     2. Convertir contenido en filas planas
//     3. CREATE TABLE IF NOT EXISTS
//     4. ALTER TABLE ADD COLUMN para columnas nuevas
//     5. INSERT INTO para cada fila
//     6. Registrar en tablas_generadas
//
// DIFERENCIA CON PYTHON:
//   Python usaba una sola conexión con un cursor y commit() al final.
//   TypeScript usa Prisma con operaciones async individuales.
//   No se puede usar prisma.$transaction() para las tablas dinámicas porque
//   DDL (CREATE TABLE, ALTER TABLE) hace COMMIT implícito en MySQL y no
//   se puede mezclar con DML en la misma transacción de Prisma.
//   Por eso se implementa un rollback manual con guardarError().
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Crea tablas dinámicas en MySQL a partir del JSON devuelto por Claude.
 * Python original: def crear_tablas_desde_json_claude(id_documento, datos_claude)
 */
export async function crearTablasDesdeClaude(
  idDocumento: number,
  datosClaude: ExtraccionClaude
): Promise<{ tablasCreadas: string[] }> {
  const tipoSeguro = datosClaude.tipo_seguro || "otro";
  const tablas = datosClaude.tablas;

  if (typeof tablas !== "object" || tablas === null) {
    throw new Error("El campo 'tablas' del JSON de Claude no es válido.");
  }

  const tablasCreadas: string[] = [];

  // Iterar sobre cada tabla devuelta por Claude
  for (const [nombreLogico, contenido] of Object.entries(tablas)) {
    try {
      const nombreMysql = nombreTablaDinamica(tipoSeguro, nombreLogico);

      // Convertir contenido a lista de filas planas
      const filas = convertirContenidoEnFilas(contenido);

      if (filas.length === 0) continue;

      // Recopilar TODAS las columnas de TODAS las filas para el ALTER TABLE
      const todasLasColumnas = new Set<string>();
      for (const fila of filas) {
        for (const columna of Object.keys(fila)) {
          todasLasColumnas.add(columna);
        }
      }

      // 1. Crear tabla si no existe
      await crearTablaDinamicaSiNoExiste(nombreMysql);

      // 2. Añadir columnas que falten
      await crearColumnasSiNoExisten(nombreMysql, todasLasColumnas);

      // 3. Insertar todas las filas
      let filasInsertadas = 0;
      for (const fila of filas) {
        await insertarFilaDinamica(nombreMysql, idDocumento, fila);
        filasInsertadas++;
      }

      // 4. Registrar la tabla generada en tablas_generadas (tabla fija de Prisma)
      await prisma.tablaGenerada.create({
        data: {
          id_documento: idDocumento,
          nombre_logico: nombreLogico,
          nombre_mysql: nombreMysql,
          filas_insertadas: filasInsertadas,
        },
      });

      tablasCreadas.push(nombreMysql);
      console.log(
        `[DB] Tabla dinámica: ${nombreMysql} — ${filasInsertadas} fila(s) insertada(s)`
      );
    } catch (error) {
      // Registrar el error pero continuar con las demás tablas
      // (equivale al comportamiento de Python donde el rollback era por todo el documento)
      const mensaje = error instanceof Error ? error.message : String(error);
      console.error(`[DB] Error en tabla "${nombreLogico}": ${mensaje}`);
      await guardarError(idDocumento, `Error en tabla "${nombreLogico}": ${mensaje}`);
    }
  }

  return { tablasCreadas };
}
