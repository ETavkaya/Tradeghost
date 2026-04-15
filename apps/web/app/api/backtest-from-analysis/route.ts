import { NextRequest } from "next/server";
import { proxyPost } from "@/app/api/_lib/proxy";

export async function POST(request: NextRequest) {
  return proxyPost(request, "/backtest-from-analysis");
}
