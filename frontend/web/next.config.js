/** @type {import('next').NextConfig} */
const nextConfig = {
  // Standalone output exists for the self-hosted Docker image (see Dockerfile).
  // Vercel builds its own output format, so skip it there — VERCEL is set on
  // every Vercel build, and nowhere else.
  output: process.env.VERCEL ? undefined : 'standalone',
  reactStrictMode: true,
};

module.exports = nextConfig;
