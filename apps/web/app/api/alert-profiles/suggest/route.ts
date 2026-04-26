import { proxyPost } from "@/app/api/_lib/proxy";

export async function POST(request: Request) {
  return proxyPost(request, "/alert-profiles/suggest");
}

