/** @type {import('next').NextConfig} */
const nextConfig = {
  basePath: "/chat",
  experimental: {
    serverActions: {
      bodySizeLimit: "10mb",
    },
  },
};

export default nextConfig;
