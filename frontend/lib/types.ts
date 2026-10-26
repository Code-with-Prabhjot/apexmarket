export type Provider = {
  node_id: string; provider_name: string; trust_tier: string; is_active: boolean;
  withdrawable_micros: number; pending_probation_micros: number; payout_pending_micros: number;
  tokens_per_sec?: number; p95_ttft_ms?: number;
};
export type TelemetryNode = {
  node_id: string; status: string; active_requests: number; p50_ttft_ms: number;
  p95_ttft_ms: number; error_rate: number; tokens_per_sec?: number;
};
export type Snapshot = {
  ts: number;
  nodes: TelemetryNode[];
  jobs: Record<string, { total: number; done: number; failovers: number }>;
  events?: Array<{ id: number; time: string; text: string; tone: string }>;
};
export type Job = {
  job_id: string; status: string; sensitivity: string; total_prompts: number;
  actual_settled_cost_micros: number; platform_fee_micros: number;
  reserved_escrow_micros: number; total_makespan_ms?: number;
};
export type BenchmarkRow = {
  run: string; route: string; cost: number; makespan: number; throughput: number; prompts: number;
};
export type Benchmark = { rows: BenchmarkRow[]; source: string; provenance: string; updated: string };
export const usd = (micros: number, digits = 6) => `$${(micros / 1_000_000).toFixed(digits)}`;
export function nodeState(node: TelemetryNode | undefined, active: boolean) {
  if (!active) return "offline";
  if (node && /SLASH|CIRCUIT_OPEN|FAIL|QUARANTIN/i.test(node.status)) return "slashed";
  if (node && (node.p95_ttft_ms > 200 || node.error_rate > 0.05)) return "slow";
  return "optimal";
}
