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

// In development the Python functions are served by scripts/devapi.py on a
// separate port, because the Vercel runtime is not running. In production
// Vercel serves /api/** itself and this rewrite is absent.
if (process.env.NODE_ENV === 'development') {
  const target = process.env.DEV_API_ORIGIN || 'http://127.0.0.1:3112';
  nextConfig.rewrites = async () => [
    { source: '/api/:path*', destination: `${target}/api/:path*` },
  ];
}

module.exports = nextConfig;
