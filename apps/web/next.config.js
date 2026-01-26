/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Allow Tailscale IP addresses for development
  allowedDevOrigins: [
    '100.117.142.1',  // Your current Tailscale IP
  ],
}

module.exports = nextConfig
