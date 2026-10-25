import { NextRequest } from "next/server";
export const dynamic = "force-dynamic";

async function proxy(request: NextRequest, { params }: { params: { path: string[] } }) {
  const route = params.path.join("/");
  const read = request.method === "GET" && /^(nodes|telemetry|jobs\/[\da-f-]+(?:\/(results|attestations))?)$/.test(route);
  const write = request.method === "POST" && /^(jobs|ledger\/settle-now|ledger\/payouts\/[\da-f-]+\/reconcile|demo\/drift)$/.test(route);
  if (!read && !write) return Response.json({ detail: "Route not allowed" }, { status: 404 });
  if (write && request.headers.get("origin") !== request.nextUrl.origin) {
    return Response.json({ detail: "A same-origin request is required." }, { status: 403 });
  }
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (process.env.APEX_CLIENT_API_KEY) headers["X-API-Key"] = process.env.APEX_CLIENT_API_KEY;
  if (request.headers.get("x-admin-key")) headers["X-Admin-Key"] = request.headers.get("x-admin-key")!;
  if (request.headers.get("idempotency-key")) headers["Idempotency-Key"] = request.headers.get("idempotency-key")!;
  try {
    const response = await fetch(`${(process.env.APEX_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "")}/api/v1/${route}`, {
      method: request.method, headers, cache: "no-store", signal: AbortSignal.timeout(30000),
      ...(write ? { body: await request.text() } : {}),
    });
    return new Response(await response.text(), { status: response.status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ detail: "The engine is unreachable. Check the backend connection and try again." }, { status: 502 });
  }
}
export { proxy as GET, proxy as POST };
