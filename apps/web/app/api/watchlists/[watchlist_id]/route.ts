import { NextRequest } from "next/server";
import { proxyDelete, proxyPut } from "@/app/api/_lib/proxy";

export async function PUT(
  request: NextRequest,
  { params }: { params: { watchlist_id: string } }
) {
  return proxyPut(request, `/watchlists/${encodeURIComponent(params.watchlist_id)}`);
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: { watchlist_id: string } }
) {
  return proxyDelete(request, `/watchlists/${encodeURIComponent(params.watchlist_id)}`);
}
