import { NextRequest } from "next/server";
import { proxyDelete, proxyPost } from "@/app/api/_lib/proxy";

export async function POST(
  request: NextRequest,
  { params }: { params: { watchlist_id: string } }
) {
  return proxyPost(request, `/watchlists/${encodeURIComponent(params.watchlist_id)}/items`);
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: { watchlist_id: string } }
) {
  return proxyDelete(request, `/watchlists/${encodeURIComponent(params.watchlist_id)}/items`);
}
