"use client";
import { useState } from "react";
import { ArrowDownRight, BarChart3, ExternalLink } from "lucide-react";
import { summarize } from "@/lib/benchmarks";
import type { Benchmark } from "@/lib/types";
export default function BenchmarkChart({ benchmark }: { benchmark: Benchmark | null }) {
  const [metric, setMetric] = useState<"cost" | "makespan">("cost");
  const [run, setRun] = useState("all");
  const [batchRatio, setBatchRatio] = useState(0.75);
  const rows = benchmark?.rows.filter(r => run === "all" || r.run === run) ?? [];
  const baseline = summarize(rows, "DEFAULT_PROVIDER_BASELINE");
  const apex = summarize(rows, "APEXMARKET_VERIFIED_ROUTER");
  const batch = summarize(rows, "BATCH_API_BASELINE");
  const comparison = [
    { label: "Single provider", value: baseline?.[metric], kind: "CSV baseline", tone: "baseline" },
    { label: "Batch API", value: batch?.[metric] ?? (metric === "cost" && baseline ? baseline.cost * batchRatio : undefined), kind: batch ? "CSV measured" : metric === "cost" ? `${Math.round(batchRatio * 100)}% price scenario` : "Asynchronous delivery", tone: "batch" },
    { label: "ApexMarket", value: apex?.[metric], kind: "CSV · includes audit overhead", tone: "apex" },
  ];
  const max = Math.max(...comparison.map(p => p.value ?? 0), 0.000001);
  const saving = baseline && apex && baseline.cost > 0 ? (1 - apex.cost / baseline.cost) * 100 : null;
  return <section className="panel benchmark-panel" id="benchmarks">
    <div className="panel-heading"><div><div className="eyebrow"><BarChart3 size={14} /> EMPIRICAL BENCHMARK</div><h2>The cost of certainty.</h2></div><span className="pill muted">{new Set(rows.map(r => r.run)).size} runs</span></div>
    <div className="chart-toolbar"><div className="segmented"><button aria-pressed={metric === "cost"} onClick={() => setMetric("cost")}>Net cost</button><button aria-pressed={metric === "makespan"} onClick={() => setMetric("makespan")}>Makespan</button></div><select aria-label="Benchmark run" value={run} onChange={e => setRun(e.target.value)}><option value="all">Average · all runs</option>{[...new Set(benchmark?.rows.map(r => r.run))].map(r => <option key={r} value={r}>Run {r}</option>)}</select></div>
    <div className="bar-chart" role="img" aria-label={`${metric} comparison: ${comparison.map(p => `${p.label} ${p.value === undefined ? p.kind : p.value}`).join(", ")}`}>
      {comparison.map(p => <div className="bar-column" key={p.label}><strong>{p.value !== undefined ? metric === "cost" ? `$${p.value.toFixed(6)}` : `${p.value.toFixed(2)}s` : "Async"}</strong><div className="bar-track"><div className={`bar ${p.tone} ${p.kind.includes("scenario") ? "scenario" : ""}`} style={{ height: `${p.value === undefined ? 12 : Math.max(5, p.value / max * 100)}%` }} /></div><b>{p.label}</b><small>{p.kind}</small></div>)}
    </div>
    <div className="chart-summary"><span><ArrowDownRight size={17} /> {saving === null ? "Benchmark comparison" : `${saving.toFixed(2)}% lower cost vs single provider`}</span><span>50 prompts / run</span></div>
    {!batch && <label className="scenario-control">Batch pricing scenario <select aria-label="Batch pricing scenario" value={batchRatio} onChange={e => setBatchRatio(Number(e.target.value))}><option value={0.75}>25% discount</option><option value={0.5}>50% discount</option><option value={1}>No discount</option></select></label>}
    <p className="fine-print">{benchmark?.provenance ?? "Loading repository benchmark…"}. Batch scenarios are illustrative, not measurements. <a href="/api/benchmarks" target="_blank" rel="noreferrer">View source <ExternalLink size={10} /></a></p>
  </section>;
}
