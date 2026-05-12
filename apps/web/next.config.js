/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    serverComponentsExternalPackages: ["pdf-parse", "tesseract.js", "@prisma/client"],
  },
};

module.exports = nextConfig;
