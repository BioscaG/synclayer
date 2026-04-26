import type { NextConfig } from "next";

const config: NextConfig = {
  reactStrictMode: true,
  async rewrites() {
    const backend = process.env.BACKEND_URL || "http://localhost:8000";
    return [
      // Proxy /api/* to FastAPI to avoid CORS during dev.
      { source: "/api/:path*", destination: `${backend}/:path*` },
    ];
  },
};

export default config;
