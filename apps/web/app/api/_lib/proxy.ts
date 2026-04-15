import { NextRequest, NextResponse } from "next/server";

const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function proxyGet(request: NextRequest, path: string): Promise<NextResponse> {
  const query = request.nextUrl.searchParams.toString();
  const url = `${backendUrl}${path}${query ? `?${query}` : ""}`;

  try {
    const response = await fetch(url, { cache: "no-store" });
    const text = await response.text();
    return new NextResponse(text, {
      status: response.status,
      headers: { "content-type": response.headers.get("content-type") ?? "application/json" }
    });
  } catch (error) {
    return NextResponse.json(
      { detail: "Backend connection failed", error: error instanceof Error ? error.message : "Unknown error" },
      { status: 502 }
    );
  }
}

export async function proxyPost(request: NextRequest, path: string): Promise<NextResponse> {
  const url = `${backendUrl}${path}`;

  try {
    const body = await request.text();
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "content-type": request.headers.get("content-type") ?? "application/json"
      },
      body
    });
    const text = await response.text();
    return new NextResponse(text, {
      status: response.status,
      headers: { "content-type": response.headers.get("content-type") ?? "application/json" }
    });
  } catch (error) {
    return NextResponse.json(
      { detail: "Backend connection failed", error: error instanceof Error ? error.message : "Unknown error" },
      { status: 502 }
    );
  }
}
