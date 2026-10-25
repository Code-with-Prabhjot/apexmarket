import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync } from "node:fs";
import { parseBenchmarks, summarize } from "../lib/benchmarks";
import { demoProviders, demoSnapshot, settleDemo } from "../lib/simulation";
import { nodeState } from "../lib/types";
test("CSV preserves three runs and measured savings without inventing Batch API results", () => {
  const rows = parseBenchmarks(readFileSync("../benchmarks/empirical_results.csv", "utf8"));
  const baseline = summarize(rows, "DEFAULT_PROVIDER_BASELINE")!;
  const apex = summarize(rows, "APEXMARKET_VERIFIED_ROUTER")!;
  assert.equal(baseline.runs, 3);
  assert.equal(((1 - apex.cost / baseline.cost) * 100).toFixed(2), "32.18");
  assert.equal(summarize(rows, "BATCH_API_BASELINE"), null);
  assert.equal(summarize(rows.filter(r => r.run === "2"), "APEXMARKET_VERIFIED_ROUTER")?.makespan, 3.92);
});
test("invalid benchmark input cannot become a chart value", () => {
  assert.throws(() => parseBenchmarks("route,cost\na,12"));
  assert.throws(() => parseBenchmarks("run_id,route_type,total_cost_usd,makespan_sec,throughput_tps,prompt_count\n1,A,no,2,3,50"));
});
test("confidential simulation sends traffic exclusively to the anchor", () => {
  const state = demoSnapshot(0, true, false, 50, 0, "job");
  assert.ok(state.nodes[0].active_requests > 0);
  assert.equal(state.nodes[1].active_requests, 0);
  assert.equal(state.nodes[2].active_requests, 0);
});
test("synthetic simulation quarantines the drifted node", () => {
  const state = demoSnapshot(0, false, true, 50, 10, "job");
  assert.ok(state.nodes[1].active_requests > 0);
  assert.equal(state.nodes[2].active_requests, 0);
  assert.equal(nodeState(state.nodes[2], true), "slashed");
  assert.equal(state.jobs.job.failovers, 12);
});
test("payout conserves micros, excludes probation, and cannot pay twice", () => {
  const settled = settleDemo(demoProviders);
  for (const [i, node] of settled.entries()) {
    assert.equal(node.withdrawable_micros + node.payout_pending_micros, demoProviders[i].withdrawable_micros);
    assert.ok(node.withdrawable_micros < 10000);
    assert.equal(node.pending_probation_micros, demoProviders[i].pending_probation_micros);
    assert.equal(node.payout_pending_micros % 10000, 0);
  }
  assert.deepEqual(settleDemo(settled), settled);
});
