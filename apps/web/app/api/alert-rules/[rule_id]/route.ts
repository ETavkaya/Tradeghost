import { NextRequest } from "next/server";
import { proxyDelete, proxyPut } from "@/app/api/_lib/proxy";

export async function PUT(
  request: NextRequest,
  { params }: { params: { rule_id: string } }
) {
  return proxyPut(request, `/alert-rules/${encodeURIComponent(params.rule_id)}`);
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: { rule_id: string } }
) {
  return proxyDelete(request, `/alert-rules/${encodeURIComponent(params.rule_id)}`);
}
