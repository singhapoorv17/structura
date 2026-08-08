/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // The Python serverless layer lives in `api/**` and is served by Vercel's
  // Python runtime, not by Next.js. Nothing here should try to compile it.
  experimental: {
    outputFileTracingExcludes: {
      '*': ['./engine/**', './export/**', './tests/**', './.venv/**', './api/**'],
    },
  },
};

module.exports = nextConfig;
