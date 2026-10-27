import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Self-contained server bundle for the Docker runtime image
  // (app/docker-compose.yml -> frontend/Dockerfile copies .next/standalone).
  output: "standalone",
  // Dev-only: extra hostnames allowed to reach the dev server (hostname only,
  // no scheme/port — see node_modules/next/dist/docs/.../allowedDevOrigins.md).
  // Without these, opening the app via 127.0.0.1 or the quick-tunnel hostname
  // makes the dev server reject the HMR WebSocket handshake, and in dev the
  // page only finishes hydration after that socket connects — the UI would
  // load but stay completely frozen (no form validation, no navigation).
  // Ignored by production builds.
  allowedDevOrigins: ["127.0.0.1", "*.trycloudflare.com"],
};

export default nextConfig;
