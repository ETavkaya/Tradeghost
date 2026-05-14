import { NextRequest } from "next/server";
import { proxyGet } from "@/app/api/_lib/proxy";

export async function GET(request: NextRequest, { params }: { params: { cohortId: string } }) {
  const mode = request.nextUrl.searchParams.get("mode");
  const qs = mode ? `?mode=${encodeURIComponent(mode)}` : "";
  return proxyGet(request, `/intelligence/cohorts/${encodeURIComponent(params.cohortId)}/export${qs}`);
}
