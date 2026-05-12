// apps/web/src/app/layout.tsx
import type { Metadata } from "next";
import { TRPCProvider } from "@/lib/trpc/provider";
import "./globals.css";

export const metadata: Metadata = {
  title: "Extractor de Pólizas — Claude AI",
  description:
    "Extrae datos estructurados de pólizas de seguros usando Claude AI y los guarda en MySQL",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="es">
      <body>
        <TRPCProvider>{children}</TRPCProvider>
      </body>
    </html>
  );
}
