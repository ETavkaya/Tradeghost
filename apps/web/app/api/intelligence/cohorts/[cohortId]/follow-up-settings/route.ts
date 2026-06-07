import { NextRequest } from "next/server";
import { proxyPut } from "@/app/api/_lib/proxy";

export async function PUT(request: NextRequest, { params }: { params: { cohortId: string } }) {
  return proxyPut(request, `/intelligence/cohorts/${encodeURIComponent(params.cohortId)}/follow-up-settings`);
}
