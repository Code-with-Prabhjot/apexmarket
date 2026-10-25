import { NextRequest } from "next/server";
export const dynamic = "force-dynamic";

async function proxy(request: NextRequest, { params }: { params: { path: string[] } }) {
  const route = params.path.join("/").replace(/\/+$/, "");
  const read =
    request.method === "GET" &&
    /^(nodes(?:\/[^/]+)?|telemetry(?:\/[^/]+)?|jobs(?:\/[^/]+(?:\/(?:results|attestations))?)?)$/.test(
      route
    );
  const write =
    request.method === "POST" &&
    /^(jobs|ledger\/settle-now|ledger\/payouts\/[^/]+\/reconcile|demo\/drift)$/.test(
      route
    );
  if (!read && !write) return Response.json({ detail: "Route not allowed" }, { status: 404 });
  if (write && request.headers.get("origin") !== request.nextUrl.origin) {
    return Response.json({ detail: "A same-origin request is required." }, { status: 403 });
  }

  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (process.env.APEX_CLIENT_API_KEY) headers["X-API-Key"] = process.env.APEX_CLIENT_API_KEY;
  if (request.headers.get("x-admin-key")) headers["X-Admin-Key"] = request.headers.get("x-admin-key")!;
  if (request.headers.get("idempotency-key")) headers["Idempotency-Key"] = request.headers.get("idempotency-key")!;

  const backendBase = (
    process.env.APEX_API_URL ||
    process.env.NEXT_PUBLIC_APEX_API_URL ||
    "http://127.0.0.1:8000"
  ).replace(/\/+$/, "");
  const targetUrl = `${backendBase}/api/v1/${route}`;

  try {
    const response = await fetch(targetUrl, {
      method: request.method,
      headers,
      cache: "no-store",
      signal: AbortSignal.timeout(30000),
      ...(write ? { body: await request.text() } : {}),
    });

    const contentType = response.headers.get("content-type") || "";
    const rawText = await response.text();

    if (!contentType.includes("application/json")) {
      console.warn(
        `[Proxy] Upstream ${targetUrl} returned non-JSON (${response.status}): ${rawText.slice(0, 100)}`
      );
      return Response.json(
        {
          detail: response.ok
            ? rawText
            : `Backend returned non-JSON response (${response.status})`,
        },
        { status: response.status }
      );
    }

    return new Response(rawText, {
      status: response.status,
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch (err) {
    console.warn(`[Proxy] Engine unreachable at ${targetUrl}:`, err);
    return Response.json(
      { detail: "The engine is unreachable. Check the backend connection and try again." },
      { status: 502 }
    );
  }
}

export { proxy as GET, proxy as POST };
