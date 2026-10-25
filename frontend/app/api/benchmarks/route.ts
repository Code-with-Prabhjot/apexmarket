import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import { parseBenchmarks } from "@/lib/benchmarks";
export const dynamic = "force-dynamic";
export async function GET() {
  try {
    const file = path.resolve(process.cwd(), "../benchmarks/empirical_results.csv");
    const [csv, info] = await Promise.all([readFile(file, "utf8"), stat(file)]);
    return Response.json({ rows: parseBenchmarks(csv), source: "benchmarks/empirical_results.csv", updated: info.mtime.toISOString(), provenance: "Repository benchmark · 3 runs · execution mode not recorded in source CSV" });
  } catch {
    return Response.json({ detail: "Benchmark data could not be read." }, { status: 503 });
  }
}
