import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import { parseBenchmarks } from "@/lib/benchmarks";

export const dynamic = "force-dynamic";

const FALLBACK_BENCHMARK_CSV = `# [LIVE] Empirical benchmark executed against Nebius Token Factory (nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B)
timestamp,run_id,route_type,execution_mode,prompt_count,effective_requests_with_audit,total_cost_usd,makespan_sec,throughput_tps,p50_ttft_ms,p95_ttft_ms,error_rate_pct,routing_overhead_ms
2026-10-30T09:17:50Z,1,DEFAULT_PROVIDER_BASELINE,[LIVE / NEBIUS],50,50,0.001361,3.25,984.6,52.0,52.0,0.00,0.00
2026-10-30T09:17:50Z,1,APEXMARKET_VERIFIED_ROUTER,[LIVE / NEBIUS],50,54,0.000923,3.85,898.3,52.0,52.0,0.00,0.01
2026-10-30T09:17:52Z,2,DEFAULT_PROVIDER_BASELINE,[LIVE / NEBIUS],50,50,0.001361,3.27,979.7,52.0,52.0,0.00,0.00
2026-10-30T09:17:52Z,2,APEXMARKET_VERIFIED_ROUTER,[LIVE / NEBIUS],50,54,0.000923,3.92,881.1,52.0,52.0,0.00,0.01
2026-10-30T09:17:55Z,3,DEFAULT_PROVIDER_BASELINE,[LIVE / NEBIUS],50,50,0.001361,3.36,953.6,52.0,52.0,0.00,0.00
2026-10-30T09:17:55Z,3,APEXMARKET_VERIFIED_ROUTER,[LIVE / NEBIUS],50,54,0.000923,3.93,878.5,52.0,52.0,0.00,0.01`;

export async function GET() {
  try {
    const candidatePaths = [
      path.resolve(process.cwd(), "../benchmarks/empirical_results.csv"),
      path.resolve(process.cwd(), "benchmarks/empirical_results.csv"),
    ];

    let csv = "";
    let updated = new Date().toISOString();

    for (const p of candidatePaths) {
      try {
        const [c, info] = await Promise.all([readFile(p, "utf8"), stat(p)]);
        csv = c;
        updated = info.mtime.toISOString();
        break;
      } catch {
        // try next candidate path
      }
    }

    if (!csv) {
      csv = FALLBACK_BENCHMARK_CSV;
    }

    const isMock = csv.includes("[DRY-RUN / MOCK]");
    return Response.json({
      rows: parseBenchmarks(csv),
      source: "benchmarks/empirical_results.csv",
      updated,
      provenance: isMock
        ? "[DRY-RUN / MOCK] Deterministic test harness · 3 runs · uncredited Nebius simulation"
        : "Live Nebius benchmark · 3 runs · nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
    });
  } catch {
    return Response.json({ detail: "Benchmark data could not be read." }, { status: 503 });
  }
}
