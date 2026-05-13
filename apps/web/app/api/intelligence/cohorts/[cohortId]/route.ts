import { NextRequest } from "next/server";
import { proxyGet } from "@/app/api/_lib/proxy";

export async function GET(request: NextRequest, { params }: { params: { cohortId: string } }) {
  return proxyGet(request, `/intelligence/cohorts/${encodeURIComponent(params.cohortId)}`);
}
