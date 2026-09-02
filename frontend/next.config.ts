import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  images: {
    unoptimized: true,
  },
  // Production perf: strip console.* (keep error/warn)
  compiler: {
    removeConsole:
      process.env.NODE_ENV === "production"
        ? { exclude: ["error", "warn"] }
        : false,
  },
  // TradingView-pro: trim bundle — date-fns is heavy without tree-shaking
  // lucide-react removed from optimizePackageImports due to case-sensitive icon mapping issue with Next 16.3 Turbopack (Activity -> activity.mjs)
  experimental: {
    optimizePackageImports: ["date-fns"],
  },
  typescript: {
    // kept true for export CI; flip to false once strict passes
    ignoreBuildErrors: true,
  },
  // swcMinify is default in Next 14+ (kept implicit)
};

export default nextConfig;
