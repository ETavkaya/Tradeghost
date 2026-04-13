import { NextRequest } from "next/server";
import { proxyGet } from "@/app/api/_lib/proxy";

export async function GET(request: NextRequest) {
  return proxyGet(request, "/backtest");
}

