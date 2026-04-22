import { NextRequest } from "next/server";
import { proxyGet, proxyPost } from "@/app/api/_lib/proxy";

export async function GET(request: NextRequest) {
  return proxyGet(request, "/monitoring/schedules");
}

export async function POST(request: NextRequest) {
  return proxyPost(request, "/monitoring/schedules");
}
