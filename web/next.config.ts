import type { NextConfig } from "next";

const API = process.env.NEURA1_API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  // A second copy (for example, one that films the demo) can build into its own folder.
  distDir: process.env.NEURA1_DIST ?? ".next",
  cacheComponents: true,
  devIndicators: false,
  experimental: {
    // Local CPU models can take minutes per answer; keep the /api proxy open (ms).
    proxyTimeout: 20 * 60 * 1000,
  },
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API}/api/:path*` }];
  },
};

export default nextConfig;
