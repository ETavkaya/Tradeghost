import { NextRequest } from "next/server";
import { proxyPut } from "@/app/api/_lib/proxy";

export async function PUT(
  request: NextRequest,
  { params }: { params: { event_id: string } }
) {
  return proxyPut(request, `/alert-events/${encodeURIComponent(params.event_id)}/status`);
}
