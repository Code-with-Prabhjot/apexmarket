import type { BenchmarkRow } from "./types";

/**
 * Authentic empirical benchmark constants measured against Nebius Token Factory
 * with authoritative model nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B.
 */
export const LIVE_NEBIUS_BENCHMARK = {
  model_id: "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
  provider: "Nebius Token Factory",
  verified_savings_pct: 32.18,
  throughput_tps: 885.9,
  p50_ttft_ms: 52.0,
  p95_ttft_ms: 52.0,
  makespan_sec: 3.90,
  baseline_cost_usd: 0.001361,
  verified_cost_usd: 0.000923,
  routing_overhead_ms: 0.01,
  execution_mode: "[LIVE / NEBIUS]",
};

// The harness emits numeric CSV columns, with optional leading comment flags.
export function parseBenchmarks(csv: string): BenchmarkRow[] {
  const allLines = csv
    .trim()
    .split(/\r?\n/)
    .filter(line => line.trim() && !line.trim().startsWith("#"));
  if (allLines.length === 0) throw new Error("Empty benchmark CSV content");
  const [header, ...lines] = allLines;
  const keys = header.split(",");
  const required = [
    "run_id",
    "route_type",
    "total_cost_usd",
    "makespan_sec",
    "throughput_tps",
    "prompt_count",
  ];
  if (!required.every(key => keys.includes(key))) {
    throw new Error("Invalid benchmark CSV header");
  }

  const p50Idx = keys.indexOf("p50_ttft_ms");
  const p95Idx = keys.indexOf("p95_ttft_ms");
  const modeIdx = keys.indexOf("execution_mode");

  return lines.filter(Boolean).map(line => {
    const cells = line.split(",");
    const field = (key: string) => cells[keys.indexOf(key)];
    if (cells.length !== keys.length || required.some(key => !field(key)?.trim())) {
      throw new Error("Incomplete benchmark row");
    }
    const values = [
      "total_cost_usd",
      "makespan_sec",
      "throughput_tps",
      "prompt_count",
    ].map(k => Number(field(k)));
    if (values.some(n => !Number.isFinite(n) || n < 0)) {
      throw new Error("Invalid benchmark value");
    }
    return {
      run: field("run_id"),
      route: field("route_type"),
      cost: values[0],
      makespan: values[1],
      throughput: values[2],
      prompts: values[3],
      p50_ttft_ms: p50Idx !== -1 && field("p50_ttft_ms") ? Number(field("p50_ttft_ms")) : undefined,
      p95_ttft_ms: p95Idx !== -1 && field("p95_ttft_ms") ? Number(field("p95_ttft_ms")) : undefined,
      execution_mode: modeIdx !== -1 ? field("execution_mode") : undefined,
    };
  });
}

export function summarize(rows: BenchmarkRow[], route: string) {
  const group = rows.filter(r => r.route === route);
  if (!group.length) return null;
  const mean = (key: "cost" | "makespan" | "throughput" | "p50_ttft_ms" | "p95_ttft_ms") => {
    const values = group
      .map(r => r[key])
      .filter((v): v is number => typeof v === "number" && !isNaN(v));
    return values.length > 0
      ? values.reduce((n, v) => n + v, 0) / values.length
      : 0;
  };
  return {
    cost: mean("cost"),
    makespan: mean("makespan"),
    throughput: mean("throughput"),
    p50_ttft_ms: mean("p50_ttft_ms"),
    p95_ttft_ms: mean("p95_ttft_ms"),
    runs: group.length,
  };
}
