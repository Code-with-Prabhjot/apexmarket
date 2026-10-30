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
  baseline_batch_api_cost_micros?: number;
};
export type BenchmarkRow = {
  run: string;
  route: string;
  cost: number;
  makespan: number;
  throughput: number;
  prompts: number;
  p50_ttft_ms?: number;
  p95_ttft_ms?: number;
  execution_mode?: string;
};
export type Benchmark = { rows: BenchmarkRow[]; source: string; provenance: string; updated: string };
export const usd = (micros: number, digits = 6) => `$${(micros / 1_000_000).toFixed(digits)}`;
export function nodeState(node: TelemetryNode | undefined, active: boolean) {
  if (!active) return "offline";
  if (node && /SLASH|CIRCUIT_OPEN|FAIL|QUARANTIN/i.test(node.status)) return "slashed";
  if (node && (node.p95_ttft_ms > 200 || node.error_rate > 0.05)) return "slow";
  return "optimal";
}

export function getProviderBadgeInfo(nodeId?: string, promptIndex: number = 0) {
  const id = (nodeId || "").toLowerCase();
  if (id.includes("nebius") || id.includes("anchor")) {
    return {
      label: "Nebius Nemotron Anchor",
      isAnchor: true,
      className: "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30",
      inRateMicros: 0.06,
      outRateMicros: 0.24,
    };
  }
  if (id.includes("community") || id.includes("spot-02") || id.includes("us-02") || promptIndex % 2 === 1) {
    return {
      label: "Community Spot L40S",
      isAnchor: false,
      className: "bg-indigo-500/15 text-indigo-300 border border-indigo-500/30",
      inRateMicros: 0.035,
      outRateMicros: 0.16,
    };
  }
  return {
    label: "RunPod H100 Spot",
    isAnchor: false,
    className: "bg-indigo-500/15 text-indigo-300 border border-indigo-500/30",
    inRateMicros: 0.04,
    outRateMicros: 0.18,
  };
}
