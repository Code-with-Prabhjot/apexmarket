import type { BenchmarkRow } from "./types";

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
    };
  });
}

export function summarize(rows: BenchmarkRow[], route: string) {
  const group = rows.filter(r => r.route === route);
  if (!group.length) return null;
  const mean = (key: "cost" | "makespan" | "throughput") =>
    group.reduce((n, r) => n + r[key], 0) / group.length;
  return {
    cost: mean("cost"),
    makespan: mean("makespan"),
    throughput: mean("throughput"),
    runs: group.length,
  };
}
