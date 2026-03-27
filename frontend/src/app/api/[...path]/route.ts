import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

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
  const targetUrl = `${BACKEND_URL}${url.pathname}${url.search}`;

  const headers = new Headers();
  request.headers.forEach((value, key) => {
    const lower = key.toLowerCase();
    if (lower !== "host" && lower !== "content-length" && lower !== "transfer-encoding") {
      headers.set(key, value);
    }
  });

  let body: ArrayBuffer | null = null;

  if (request.method !== "GET" && request.method !== "HEAD") {
    const contentType = request.headers.get("content-type") || "";
    if (contentType) {
      headers.set("content-type", contentType);
    }
    body = await request.arrayBuffer();
  }

  const resp = await fetch(targetUrl, {
    method: request.method,
    headers,
    body,
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
