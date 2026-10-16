import type { NextConfig } from "next";

const API = process.env.NEURA1_API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  cacheComponents: true,
  devIndicators: false,
  compiler: {
    // SuperDoc (the Word editor) is built on Vue; set its build flags explicitly.
    define: { __VUE_OPTIONS_API__: "true", __VUE_PROD_DEVTOOLS__: "false", __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: "false" },
  },
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
