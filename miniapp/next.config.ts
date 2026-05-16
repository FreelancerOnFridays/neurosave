import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // /api/* is handled by app/api/[...slug]/route.ts which explicitly forwards Authorization headers.
  // Allow ngrok (and any dev tunnel) to receive HMR updates.
  allowedDevOrigins: ["*.ngrok-free.app", "*.ngrok.io", "*.ngrok.dev", "taste-outscore-stargazer.ngrok-free.dev"],
};

export default nextConfig;
