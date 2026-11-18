import { NextRequest } from "next/server";
import { proxyPost } from "@/app/api/_lib/proxy";

export async function POST(
  request: NextRequest,
  { params }: { params: { experimentId: string } },
) {
  return proxyPost(request, `/intelligence/strategy-lab/experiments/${encodeURIComponent(params.experimentId)}/activate`);
}
