import { NextRequest } from "next/server";
import { proxyGet } from "@/app/api/_lib/proxy";

export async function GET(
  request: NextRequest,
  { params }: { params: { cohortId: string; reportDate: string } }
) {
  return proxyGet(
    request,
    `/cohorts/${encodeURIComponent(params.cohortId)}/daily-reports/${encodeURIComponent(params.reportDate)}`
  );
}
