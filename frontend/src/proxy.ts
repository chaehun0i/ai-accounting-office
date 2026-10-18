import { NextResponse, type NextRequest } from "next/server";

export function proxy(request: NextRequest) {
  // Keep credentials and query values out of the container's request log.
  console.info(`[frontend] ${request.method} ${request.nextUrl.pathname}`);
  return NextResponse.next();
}

export const config = {
  matcher: ["/", "/((?!_next/static|_next/image|favicon.ico).*)"],
};
