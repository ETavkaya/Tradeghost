import { NextRequest } from "next/server";
import { proxyGet } from "@/app/api/_lib/proxy";

export async function GET(
  request: NextRequest,
  { params }: { params: { snapshot_id: string } }
) {
  return proxyGet(request, `/backtest-snapshots/${encodeURIComponent(params.snapshot_id)}`);
}