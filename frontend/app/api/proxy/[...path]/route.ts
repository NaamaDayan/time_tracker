import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";
const API_KEY = process.env.API_KEY ?? "dev-only-change-me";

async function proxyRequest(request: NextRequest, path: string[]) {
  const url = new URL(`${BACKEND}/api/v1/${path.join("/")}`);
  request.nextUrl.searchParams.forEach((v, k) => url.searchParams.set(k, v));

  try {
    const res = await fetch(url.toString(), {
      method: request.method,
      headers: {
        "X-API-Key": API_KEY,
        "Content-Type": request.headers.get("Content-Type") ?? "application/json",
      },
      body: request.method !== "GET" && request.method !== "HEAD" ? await request.text() : undefined,
      cache: "no-store",
    });
    if (res.status === 204) {
      return new NextResponse(null, { status: 204 });
    }
    const body = await res.text();
    return new NextResponse(body, {
      status: res.status,
      headers: { "Content-Type": res.headers.get("Content-Type") ?? "application/json" },
    });
  } catch (err) {
    const message =
      err instanceof Error && "cause" in err && err.cause instanceof Error
        ? err.cause.message
        : err instanceof Error
          ? err.message
          : "Backend unreachable";
    return NextResponse.json(
      {
        detail: `Cannot reach API at ${BACKEND}. Start the backend: cd backend && uvicorn app.main:app --reload (${message})`,
      },
      { status: 503 }
    );
  }
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  return proxyRequest(request, path);
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  return proxyRequest(request, path);
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  return proxyRequest(request, path);
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  return proxyRequest(request, path);
}
