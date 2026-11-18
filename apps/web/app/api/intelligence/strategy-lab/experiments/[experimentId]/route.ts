import { NextRequest } from "next/server";
import { proxyGet } from "@/app/api/_lib/proxy";

export async function GET(
  request: NextRequest,
  { params }: { params: { experimentId: string } },
) {
  return proxyGet(request, `/intelligence/strategy-lab/experiments/${encodeURIComponent(params.experimentId)}`);
}
