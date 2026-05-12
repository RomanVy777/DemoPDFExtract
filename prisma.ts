// apps/web/src/lib/prisma.ts
// ─────────────────────────────────────────────────────────────────────────────
// SINGLETON DE PRISMA CLIENT
//
// DIFERENCIA CON PYTHON:
//   En Python, database_manager.py abría y cerraba una conexión mysql.connector
//   en cada función (conectar() / cursor.close() / conexion.close()).
//   En Node.js con Next.js el hot-reload en desarrollo puede crear múltiples
//   instancias de PrismaClient que agotan el pool de conexiones de MySQL.
//
//   La solución estándar es guardar la instancia en globalThis durante desarrollo
//   para reutilizarla entre hot-reloads. En producción se crea una sola vez.
//
// TRADUCCIÓN:
//   Python: mysql.connector.connect(**config) → cada llamada abre/cierra
//   TypeScript: PrismaClient singleton → una instancia, pool de conexiones
// ─────────────────────────────────────────────────────────────────────────────

import { PrismaClient } from "@prisma/client";

// Declaramos la variable en el scope global de Node.js para sobrevivir HMR
const globalForPrisma = globalThis as unknown as {
  prisma: PrismaClient | undefined;
};

export const prisma =
  globalForPrisma.prisma ??
  new PrismaClient({
    // En desarrollo: loguear todas las queries SQL para debuggear
    // Equivalente a activar console.log en Python antes de cursor.execute()
    log: process.env.NODE_ENV === "development" ? ["query", "error", "warn"] : ["error"],
  });

// Solo en desarrollo guardamos en global para evitar múltiples instancias
if (process.env.NODE_ENV !== "production") {
  globalForPrisma.prisma = prisma;
}
