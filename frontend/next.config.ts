import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Hide the round "N" development badge (it sits on top of the UI, and in screenshots).
  // Compile and runtime errors are still shown.
  devIndicators: false,
};

export default nextConfig;
