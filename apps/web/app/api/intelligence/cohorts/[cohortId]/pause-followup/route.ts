import { NextRequest } from "next/server";
import { proxyPost } from "@/app/api/_lib/proxy";

export async function POST(request: NextRequest, { params }: { params: { cohortId: string } }) {
  return proxyPost(request, `/intelligence/cohorts/${encodeURIComponent(params.cohortId)}/pause-followup`);
}
