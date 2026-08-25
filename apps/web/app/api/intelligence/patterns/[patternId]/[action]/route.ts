import { NextRequest, NextResponse } from "next/server";
import { proxyPost } from "@/app/api/_lib/proxy";

const actions = new Set(["approve", "reject"]);

export async function POST(
  request: NextRequest,
  { params }: { params: { patternId: string; action: string } }
) {
  if (!actions.has(params.action)) {
    return NextResponse.json({ detail: "Unsupported pattern review action." }, { status: 404 });
  }
  return proxyPost(
    request,
    `/intelligence/patterns/${encodeURIComponent(params.patternId)}/${params.action}`
  );
}
