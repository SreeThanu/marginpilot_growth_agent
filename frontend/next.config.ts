import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // This repository already carries its own CLAUDE.md; Next's generated one
  // would sit beside it saying something different.
  agentRules: false,
};

export default nextConfig;
