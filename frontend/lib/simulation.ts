import type { Provider, Snapshot } from "./types";

export const demoProviders: Provider[] = [
  { node_id: "nebius-anchor", provider_name: "Nebius Anchor", trust_tier: "ANCHOR", is_active: true, withdrawable_micros: 1834560, pending_probation_micros: 0, payout_pending_micros: 0 },
  { node_id: "spot-eu-01", provider_name: "Spot · Europe", trust_tier: "VERIFIED_PROVIDER", is_active: true, withdrawable_micros: 736250, pending_probation_micros: 12450, payout_pending_micros: 0 },
  { node_id: "spot-us-02", provider_name: "Spot · US East", trust_tier: "PROBATION_SPOT", is_active: true, withdrawable_micros: 426720, pending_probation_micros: 8430, payout_pending_micros: 0 },
];
export function demoSnapshot(tick: number, confidential: boolean, slashed: boolean, total: number, done: number, jobId?: string): Snapshot {
  return {
    ts: Date.now() / 1000,
    nodes: demoProviders.map((p, i) => {
      const enabled = confidential ? i === 0 : !(slashed && i === 2);
      const running = enabled && done < total;
      return { node_id: p.node_id, status: slashed && i === 2 ? "SLASHED" : "ACTIVE", active_requests: running ? [8, 10, 6][i] : 0,
        p50_ttft_ms: [52, 41, 93][i], p95_ttft_ms: [68, 64, slashed ? 420 : 248][i] + (tick % 4),
        error_rate: slashed && i === 2 ? 0.24 : 0, tokens_per_sec: running ? [312, 378, 198][i] + tick % 17 : 0 };
    }),
    jobs: jobId ? { [jobId]: { total, done, failovers: slashed ? Math.min(12, total) : 0 } } : {},
  };
}
export function settleDemo(providers: Provider[]) {
  return providers.map(p => {
    const payable = Math.floor(p.withdrawable_micros / 10000) * 10000;
    return { ...p, withdrawable_micros: p.withdrawable_micros - payable, payout_pending_micros: p.payout_pending_micros + payable };
  });
}
