import { NextRequest } from "next/server";
import { proxyDelete, proxyPut } from "@/app/api/_lib/proxy";

export async function PUT(
  request: NextRequest,
  { params }: { params: { schedule_id: string } }
) {
  return proxyPut(request, `/monitoring/schedules/${encodeURIComponent(params.schedule_id)}`);
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: { schedule_id: string } }
) {
  return proxyDelete(request, `/monitoring/schedules/${encodeURIComponent(params.schedule_id)}`);
}
