import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

// Allow large uploads (2GB video files)
export const runtime = "nodejs";
export const maxDuration = 300;

export async function GET(request: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(request, params.path);
}

export async function POST(request: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(request, params.path);
}

export async function DELETE(request: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(request, params.path);
}

export async function PUT(request: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(request, params.path);
}

async function proxy(request: NextRequest, pathSegments: string[]) {
  const url = new URL(request.url);
  // Preserve the original path including trailing slash
  const originalPath = url.pathname.replace(/^\/?/, "");
  const targetUrl = `${BACKEND_URL}/${originalPath}${url.search}`;

  const headers = new Headers();
  request.headers.forEach((value, key) => {
    if (key.toLowerCase() !== "host" && key.toLowerCase() !== "content-length") {
      headers.set(key, value);
    }
  });

  let body: BodyInit | null = null;

  if (request.method !== "GET" && request.method !== "HEAD") {
    // Stream the body directly — don't buffer large uploads in memory
    body = request.body as ReadableStream<Uint8Array> | null;
    const contentType = request.headers.get("content-type");
    if (contentType) {
      headers.set("content-type", contentType);
    }
  }

  const resp = await fetch(targetUrl, {
    method: request.method,
    headers,
    body,
    // @ts-expect-error - Node.js fetch supports duplex for streaming
    duplex: "half",
  });

  const respHeaders = new Headers();
  resp.headers.forEach((value, key) => {
    respHeaders.set(key, value);
  });

  return new NextResponse(resp.body, {
    status: resp.status,
    statusText: resp.statusText,
    headers: respHeaders,
  });
}
