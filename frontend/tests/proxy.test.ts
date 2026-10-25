import { test } from "node:test";
import assert from "node:assert/strict";
import { NextRequest } from "next/server";
import { POST, GET } from "../app/api/backend/[...path]/route";

test("proxy rejects arbitrary paths and cross-origin mutations before contacting backend", async () => {
  const denied = await GET(new NextRequest("http://localhost:3000/api/backend/admin"), { params: { path: ["admin"] } });
  assert.equal(denied.status, 404);
  const csrf = await POST(new NextRequest("http://localhost:3000/api/backend/jobs", { method: "POST", headers: { origin: "https://untrusted.example" }, body: "{}" }), { params: { path: ["jobs"] } });
  assert.equal(csrf.status, 403);
});
test("proxy forwards exact body and admin idempotency headers, without leaking server key in response", async () => {
  const original = global.fetch;
  const previous = process.env.APEX_CLIENT_API_KEY;
  process.env.APEX_CLIENT_API_KEY = "server-secret";
  let calls = 0;
  global.fetch = async (url, options) => {
    calls++;
    assert.equal(String(url), "http://127.0.0.1:8000/api/v1/ledger/settle-now");
    assert.equal((options?.headers as Record<string, string>)["X-API-Key"], "server-secret");
    assert.equal((options?.headers as Record<string, string>)["X-Admin-Key"], "admin-session");
    assert.equal((options?.headers as Record<string, string>)["Idempotency-Key"], "same-request");
    assert.equal(options?.body, "{}");
    return Response.json({ status: "SUBMITTED_PENDING" });
  };
  try {
    const result = await POST(new NextRequest("http://localhost:3000/api/backend/ledger/settle-now", { method: "POST", headers: { origin: "http://localhost:3000", "X-Admin-Key": "admin-session", "Idempotency-Key": "same-request" }, body: "{}" }), { params: { path: ["ledger", "settle-now"] } });
    assert.equal(calls, 1);
    assert.equal(result.status, 200);
    assert.deepEqual(await result.json(), { status: "SUBMITTED_PENDING" });
  } finally {
    global.fetch = original;
    if (previous === undefined) delete process.env.APEX_CLIENT_API_KEY; else process.env.APEX_CLIENT_API_KEY = previous;
  }
});
