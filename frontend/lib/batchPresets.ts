/**
 * Industry Batch Presets (1-Click Enterprise Datasets)
 * Provides production-grade benchmark datasets for financial sentiment,
 * HIPAA clinical extraction, and high-throughput synthetic code verification.
 */

export interface IndustryBatchPreset {
  id: string;
  title: string;
  tag: string;
  category: "finance" | "healthcare" | "engineering";
  description: string;
  promptCount: number;
  sensitivity: "CONFIDENTIAL" | "SYNTHETIC" | "PUBLIC";
  budget: string;
  maxTokens: number;
  prompts: string[];
}

export const INDUSTRY_BATCH_PRESETS: IndustryBatchPreset[] = [
  {
    id: "sec-10k",
    title: "SEC 10-K Financial Sentiment",
    tag: "50 Prompts · Spot Arbitrage",
    category: "finance",
    description: "Enterprise sentiment & risk disclosure analysis across 50 corporate liquidity and EBITDA covenant filings.",
    promptCount: 50,
    sensitivity: "PUBLIC",
    budget: "1.00",
    maxTokens: 512,
    prompts: Array.from({ length: 50 }, (_, i) => {
      const companies = ["Alphabet", "NVIDIA", "Microsoft", "Amazon", "Apple", "Meta", "Tesla", "Palantir", "Snowflake", "Datadog"];
      const company = companies[i % companies.length];
      const metrics = [
        "operating cash flow ratio and interest coverage leverage under higher SOFR base rates",
        "EBITDA margin compression risk from datacenter GPU depreciation schedules",
        "contingent liabilities and debt covenant compliance under macroeconomic downturns",
        "working capital liquidity reserve requirements and revolving credit drawdowns",
        "unearned revenue backlog and multi-year cloud infrastructure commitment liabilities"
      ];
      const metric = metrics[i % metrics.length];
      return `Analyze SEC 10-K Item 7 (MD&A) for ${company} (Filing Section #${i + 1}): Extract quantitative indicators for ${metric}. Provide risk rating (Low/Medium/High) and 1-sentence rationale.`;
    }),
  },
  {
    id: "hipaa-medical",
    title: "HIPAA Medical Extraction",
    tag: "25 Prompts · Confidential Air-Gap",
    category: "healthcare",
    description: "Clinical documentation & ICD-10 extraction. Auto-selects CONFIDENTIAL air-gap mode, routing 100% to Nebius Anchor.",
    promptCount: 25,
    sensitivity: "CONFIDENTIAL",
    budget: "1.50",
    maxTokens: 512,
    prompts: Array.from({ length: 25 }, (_, i) => {
      const scenarios = [
        "Patient presents with acute exacerbation of chronic obstructive pulmonary disease (COPD) with hypoxemic respiratory failure.",
        "Clinical discharge summary notes post-operative day 3 following coronary artery bypass graft with transient atrial fibrillation.",
        "Pharmacotherapy evaluation for type 2 diabetes mellitus with nephropathy and concomitant hypertension on ACE inhibitors.",
        "Neurological examination findings documenting mild cognitive impairment with amyloid biomarker confirmation.",
        "Oncology tumor board notes discussing adjuvant immunotherapy following resection of stage IIIA melanoma."
      ];
      const scenario = scenarios[i % scenarios.length];
      return `[CONFIDENTIAL PHI EVALUATION #${i + 1}] Review clinical documentation: "${scenario}". Extract primary ICD-10 diagnosis codes, recommended contraindication checks, and de-identify all entity references according to HIPAA Safe Harbor guidelines.`;
    }),
  },
  {
    id: "code-canary",
    title: "High-Throughput Synthetic Code Canary",
    tag: "100 Prompts · Swarm + 4% Canary",
    category: "engineering",
    description: "Distributed algorithm verification across spot swarm with active rotated arithmetic and JSON canaries.",
    promptCount: 100,
    sensitivity: "SYNTHETIC",
    budget: "2.00",
    maxTokens: 256,
    prompts: Array.from({ length: 100 }, (_, i) => {
      if (i % 25 === 0) {
        // Rotated deterministic canary prompt
        const n1 = 17 + i * 3;
        const n2 = 43 + i * 2;
        return `Calculate step-by-step the sum of ${n1} and ${n2}. Respond with only the exact integer sum.`;
      }
      const algorithms = [
        "Implement a thread-safe lock-free ring buffer in modern Rust with AtomicUsize head/tail pointers.",
        "Write a distributed Raft log compaction compaction handler in Go with snapshot chunk streaming.",
        "Design a Bloom filter in TypeScript using double-hashing with murmur3 and xxHash algorithms.",
        "Construct an optimal bounded priority queue with min-max heap properties in Python.",
        "Synthesize an AVX-512 vectorization kernel in C++ for cosine similarity over float32 embedding arrays."
      ];
      const algo = algorithms[i % algorithms.length];
      return `[SYNTHETIC KERNEL #${i + 1}] ${algo} Include asymptotic complexity analysis and strict boundary test assertions.`;
    }),
  },
];
