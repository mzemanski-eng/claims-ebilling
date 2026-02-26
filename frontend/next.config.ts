import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Allow cross-origin requests to the Render API in dev
  async rewrites() {
    return [];
  },
};

export default nextConfig;
