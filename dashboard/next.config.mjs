/** @type {import('next').NextConfig} */
const nextConfig = {
  // The dashboard talks to the backend only through its own Route Handlers
  // (server proxy), so no browser-level backend origin is needed.
  reactStrictMode: true,
};

export default nextConfig;