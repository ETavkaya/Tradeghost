import { NextRequest } from "next/server";
import { proxyPost } from "@/app/api/_lib/proxy";

export async function POST(
  request: NextRequest,
  { params }: { params: { snapshot_id: string } }
) {
  return proxyPost(request, `/backtest-snapshots/${encodeURIComponent(params.snapshot_id)}/comments`);
}