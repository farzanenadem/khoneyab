// The browser only talks to Next.js; /api/* is proxied to the FastAPI backend,
// so the backend URL stays server-side.
const API_URL = (process.env.JOB_API_URL || "http://localhost:8000").replace(/\/$/, "");

/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/:path*` }];
  },
  images: { unoptimized: true },
  // The LLM agent (/chat) can take longer than the default 30 s proxy timeout.
  experimental: { proxyTimeout: 120000 },
};

export default nextConfig;
