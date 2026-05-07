import { NextRequest } from "next/server";
import { proxyGet } from "@/app/api/_lib/proxy";

export async function GET(request: NextRequest, { params }: { params: { runId: string } }) {
  return proxyGet(request, `/intelligence/report/${encodeURIComponent(params.runId)}`);
}
