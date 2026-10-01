import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Self-contained server bundle for the Docker runtime image
  // (app/docker-compose.yml -> frontend/Dockerfile copies .next/standalone).
  output: "standalone",
};

export default nextConfig;
