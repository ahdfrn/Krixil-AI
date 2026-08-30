import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async headers() {
    // Conservative, deployment-agnostic headers only. Deliberately no Content-Security-Policy
    // here — getting one right needs testing against a real deployed environment (easy to
    // silently break Radix UI portals or Tailwind's runtime styles), and there's no deploy target
    // yet to validate one against. See docs/architecture/web-phase5.md.
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        ],
      },
    ];
  },
};

export default nextConfig;
