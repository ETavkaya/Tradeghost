import { NextRequest, NextResponse } from "next/server";
import { proxyDelete, proxyGet, proxyPost } from "@/app/api/_lib/proxy";

export async function GET(request: NextRequest, { params }: { params: { cohortId: string } }) {
  return proxyGet(request, `/intelligence/cohorts/${encodeURIComponent(params.cohortId)}`);
}

export async function DELETE(request: NextRequest, { params }: { params: { cohortId: string } }) {
  return proxyDelete(request, `/intelligence/cohorts/${encodeURIComponent(params.cohortId)}`);
}

export async function POST(request: NextRequest, { params }: { params: { cohortId: string } }) {
  const action = request.nextUrl.searchParams.get("action");
  if (action === "archive") {
    return proxyPost(request, `/intelligence/cohorts/${encodeURIComponent(params.cohortId)}/archive`);
  }
  if (action === "activate") {
    return proxyPost(request, `/intelligence/cohorts/${encodeURIComponent(params.cohortId)}/activate`);
  }
  return NextResponse.json(
    { detail: "Invalid cohort action", action, supported_actions: ["archive", "activate"] },
    { status: 400 },
  );
}
