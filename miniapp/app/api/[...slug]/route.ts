import { type NextRequest } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Params = Promise<{ slug: string[] }>;

async function proxy(request: NextRequest, params: Params): Promise<Response> {
  const { slug } = await params;
  const search = request.nextUrl.search;
  const url = `${BACKEND}/api/${slug.join("/")}${search}`;

  // Explicitly copy all headers so Authorization is never lost
  const headers: Record<string, string> = {};
  request.headers.forEach((value, key) => {
    if (key.toLowerCase() !== "host") {
      headers[key] = value;
    }
  });

  console.log("[proxy]", request.method, url, "auth:", headers["authorization"] ?? "MISSING");

  const init: RequestInit = { method: request.method, headers };
  if (request.method !== "GET" && request.method !== "HEAD") {
    // @ts-expect-error duplex is required for streaming bodies in Node.js fetch
    init.duplex = "half";
    init.body = request.body;
  }
  return fetch(url, init);
}

export const GET = (req: NextRequest, { params }: { params: Params }) =>
  proxy(req, params);
export const POST = (req: NextRequest, { params }: { params: Params }) =>
  proxy(req, params);
export const PUT = (req: NextRequest, { params }: { params: Params }) =>
  proxy(req, params);
export const PATCH = (req: NextRequest, { params }: { params: Params }) =>
  proxy(req, params);
export const DELETE = (req: NextRequest, { params }: { params: Params }) =>
  proxy(req, params);
