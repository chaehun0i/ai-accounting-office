import type { NextConfig } from "next";

const origin = process.env.BACKEND_API_ORIGIN ?? "http://127.0.0.1:8000";
const parsed = new URL(origin);
if (!["http:", "https:"].includes(parsed.protocol) || parsed.username || parsed.password || parsed.search || parsed.hash || parsed.pathname !== "/") {
  throw new Error("백엔드 주소는 로그인 정보와 경로가 없는 HTTP(S) origin으로 설정해 주세요.");
}
const nextConfig: NextConfig = {
  poweredByHeader: false,
  reactStrictMode: true,
  async rewrites() { return [{ source: "/api/:path*", destination: `${parsed.origin}/:path*` }]; },
};
export default nextConfig;
