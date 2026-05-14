import type { NextConfig } from "next";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  // Proxy /api/* to the Python backend so a single ngrok tunnel covers both frontend and API.
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${apiUrl}/api/:path*`,
      },
    ];
  },
  // Allow ngrok (and any dev tunnel) to receive HMR updates.
  allowedDevOrigins: ["*.ngrok-free.app", "*.ngrok.io", "*.ngrok.dev","taste-outscore-stargazer.ngrok-free.dev"],
};

export default nextConfig;
