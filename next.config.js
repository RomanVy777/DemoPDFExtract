/** @type {import('next').NextConfig} */
const nextConfig = {
  // Permite que pdf-parse y tesseract.js funcionen en el servidor Node.js
  // sin que Next.js intente empaquetarlos para el browser (que fallaría).
  // Equivalente en Python: simplemente importar las libs en el módulo del servidor.
  serverExternalPackages: ["pdf-parse", "tesseract.js"],

  experimental: {
    // Necesario para que tRPC pueda usar el App Router de Next.js 14
    serverComponentsExternalPackages: ["@prisma/client"],
  },

  // Aumentar el límite de tamaño del body para la subida de PDFs grandes
  // En Python no había este límite porque era una app de escritorio local.
  api: {
    bodyParser: {
      sizeLimit: "50mb",
    },
    responseLimit: "50mb",
  },
};

module.exports = nextConfig;
