import { NextRequest } from "next/server";
import { proxyPost } from "@/app/api/_lib/proxy";

export async function POST(request: NextRequest, { params }: { params: { cohortId: string } }) {
  const query = request.nextUrl.searchParams.toString();
  return proxyPost(
    request,
    `/cohorts/${encodeURIComponent(params.cohortId)}/daily-reports/run${query ? `?${query}` : ""}`
  );
}
