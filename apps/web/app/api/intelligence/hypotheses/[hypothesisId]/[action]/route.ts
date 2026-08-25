import { NextRequest, NextResponse } from "next/server";
import { proxyPost } from "@/app/api/_lib/proxy";

const actions = new Set(["accept", "reject"]);

export async function POST(
  request: NextRequest,
  { params }: { params: { hypothesisId: string; action: string } }
) {
  if (!actions.has(params.action)) {
    return NextResponse.json({ detail: "Unsupported hypothesis review action." }, { status: 404 });
  }
  return proxyPost(
    request,
    `/intelligence/hypotheses/${encodeURIComponent(params.hypothesisId)}/${params.action}`
  );
}
