import { NextRequest } from "next/server";
import { proxyGet } from "@/app/api/_lib/proxy";

export async function GET(request: NextRequest) {
  const query = request.nextUrl.searchParams.toString();
  return proxyGet(request, `/logs/files/read${query ? `?${query}` : ""}`);
}
