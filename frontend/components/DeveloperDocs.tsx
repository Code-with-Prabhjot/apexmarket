"use client";
import React, { useState } from "react";
import {
  Code2,
  Terminal,
  FileCode,
  Copy,
  Check,
  ExternalLink,
  ShieldCheck,
  Zap,
  Key,
  BookOpen,
} from "lucide-react";

export default function DeveloperDocs() {
  const [activeTab, setActiveTab] = useState<"python" | "curl" | "typescript">("python");
  const [copied, setCopied] = useState(false);

  const snippets = {
    python: `# Install: pip install apexmarket-sdk
import apexmarket

# Initialize authenticated client
client = apexmarket.Client(
    api_key="am_live_prod_9f82c47a110e8b2",
    base_url="https://api.apexmarket.internal"
)

# Submit batch inference with fail-closed privacy & 5-tier verification
job = client.batch.create(
    prompts=[
        "Analyze quarterly revenue drift across enterprise cloud contracts...",
        "Extract structured EBITDA margin risk disclosures from 10-K..."
    ],
    sensitivity="CONFIDENTIAL",  # Forces 100% Nebius Nemotron Anchor routing
    max_tokens_per_prompt=512,
    max_cost_ceiling_usd=1.00,
    makespan_sla_seconds=120.0
)

print(f"Batch {job.id} dispatched to cluster.")

# Await reassembled outputs & verified cryptographic proof
results = job.wait_for_completion(poll_interval=2.0)

print(f"Execution Status: {results.status}")
print(f"Verified Savings: {results.savings_percentage}% (vs baseline)")
print(f"Server Attestation: {results.attestation_hash}")

for prompt_item in results.items:
    print(f"Prompt #{prompt_item.index}: {prompt_item.output[:60]}...")
`,

    curl: `# 1. Ingest Batch Inference Job
curl -X POST https://api.apexmarket.internal/api/v1/jobs \\
  -H "Content-Type: application/json" \\
  -H "X-API-Key: am_live_prod_9f82c47a110e8b2" \\
  -d '{
    "sensitivity": "CONFIDENTIAL",
    "target_model": "nvidia/nemotron-3-nano-30b-a3b",
    "max_tokens_per_prompt": 512,
    "max_cost_ceiling_micros": 1000000,
    "makespan_sla_seconds": 120.0,
    "prompts": [
      {
        "prompt_index": 0,
        "content": "Analyze enterprise liquidity ratios under higher SOFR base rates."
      },
      {
        "prompt_index": 1,
        "content": "Extract SEC 10-K risk indicators for GPU infrastructure depreciation."
      }
    ]
  }'

# 2. Query Reassembled Results
# curl -X GET https://api.apexmarket.internal/api/v1/jobs/{job_id}/results \\
#   -H "X-API-Key: am_live_prod_9f82c47a110e8b2"

# 3. Retrieve 5-Tier Cryptographic Proof
# curl -X GET https://api.apexmarket.internal/api/v1/jobs/{job_id}/attestations \\
#   -H "X-API-Key: am_live_prod_9f82c47a110e8b2"
`,

    typescript: `// Install: npm install @apexmarket/sdk
import { ApexMarketClient } from "@apexmarket/sdk";

// Initialize client
const client = new ApexMarketClient({
  apiKey: process.env.APEXMARKET_API_KEY || "am_live_prod_9f82c47a110e8b2",
  baseUrl: "https://api.apexmarket.internal",
});

async function main() {
  // Dispatch batch with confidential air-gap
  const batch = await client.batches.create({
    sensitivity: "CONFIDENTIAL",
    maxCostCeilingUsd: 1.00,
    maxTokensPerPrompt: 512,
    prompts: [
      "Analyze quarterly revenue drift across enterprise cloud contracts...",
      "Extract structured EBITDA margin risk disclosures from 10-K..."
    ],
  });

  console.log(\`Batch \${batch.id} submitted.\`);

  // Wait for 5-tier verification and reassembly
  const results = await batch.waitForCompletion();

  console.log(\`Verified Savings: \${results.savingsPercentage}%\`);
  console.log(\`Cryptographic Attestation: \${results.attestationHash}\`);

  for (const item of results.items) {
    console.log(\`[#\${item.promptIndex}] \${item.outputText.slice(0, 50)}...\`);
  }
}

main().catch(console.error);
`,
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(snippets[activeTab]);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <section className="panel docs-panel" id="docs" style={{ marginTop: 24 }}>
      <div className="flex items-center justify-between pb-4 border-b border-[#202c3c]">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-[#70e4bf1f] border border-[#70e4bf44] flex items-center justify-center text-[#70e4bf]">
            <Code2 size={22} />
          </div>
          <div>
            <h2 className="text-base font-bold text-slate-100 flex items-center gap-2">
              Developer API & SDK Quickstart
              <span className="px-2 py-0.5 text-[10px] font-bold rounded bg-emerald-500/10 text-[#70e4bf] border border-[#70e4bf44]">
                v3.0.0 Enterprise
              </span>
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Programmatic batch submission, cryptographic verification webhooks, and PayPal escrow settlement.
            </p>
          </div>
        </div>

        {/* Tab Switcher */}
        <div className="flex items-center gap-1 p-1 rounded-lg bg-[#0e1622] border border-[#202c3c]">
          <button
            onClick={() => setActiveTab("python")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-colors ${
              activeTab === "python"
                ? "bg-[#70e4bf] text-[#06231a] shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <FileCode size={14} /> Python SDK
          </button>
          <button
            onClick={() => setActiveTab("curl")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-colors ${
              activeTab === "curl"
                ? "bg-[#70e4bf] text-[#06231a] shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Terminal size={14} /> cURL / REST
          </button>
          <button
            onClick={() => setActiveTab("typescript")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-colors ${
              activeTab === "typescript"
                ? "bg-[#70e4bf] text-[#06231a] shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Code2 size={14} /> Node.js / TS
          </button>
        </div>
      </div>

      {/* Code Container */}
      <div className="relative mt-4 rounded-xl bg-[#090e17] border border-[#202c3c] overflow-hidden">
        <div className="flex items-center justify-between px-4 py-2.5 bg-[#0e1624] border-b border-[#202c3c]">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-red-500/80" />
            <span className="w-2.5 h-2.5 rounded-full bg-yellow-500/80" />
            <span className="w-2.5 h-2.5 rounded-full bg-green-500/80" />
            <span className="text-[11px] font-mono text-slate-400 ml-2">
              {activeTab === "python"
                ? "batch_submit.py"
                : activeTab === "curl"
                ? "curl_request.sh"
                : "batch_submit.ts"}
            </span>
          </div>
          <button
            onClick={handleCopy}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-semibold bg-[#1a2638] hover:bg-[#22334a] text-slate-200 border border-[#2a3c54] transition-colors"
          >
            {copied ? <Check size={13} className="text-[#70e4bf]" /> : <Copy size={13} />}
            {copied ? "Copied!" : "Copy Snippet"}
          </button>
        </div>

        <pre className="p-4 text-xs font-mono text-slate-200 overflow-x-auto leading-relaxed selection:bg-[#70e4bf33]">
          <code>{snippets[activeTab]}</code>
        </pre>
      </div>

      {/* API Reference Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-4 pt-4 border-t border-[#202c3c]">
        <div className="p-3 rounded-lg bg-[#0e1622] border border-[#202c3c]">
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-200 mb-1">
            <Key size={14} className="text-[#edbb72]" /> Authentication
          </div>
          <p className="text-[11px] text-slate-400 leading-normal">
            Pass <code className="text-[#70e4bf]">X-API-Key: am_live_...</code> in HTTP headers or configure via SDK client initialization.
          </p>
        </div>

        <div className="p-3 rounded-lg bg-[#0e1622] border border-[#202c3c]">
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-200 mb-1">
            <ShieldCheck size={14} className="text-[#70e4bf]" /> Proof Before Payment
          </div>
          <p className="text-[11px] text-slate-400 leading-normal">
            Every shred is verified through 5 tiers. PayPal escrow pays providers only upon cryptographic proof verification.
          </p>
        </div>

        <div className="p-3 rounded-lg bg-[#0e1622] border border-[#202c3c]">
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-200 mb-1">
            <Zap size={14} className="text-[#70e4bf]" /> Sub-Cent Ledger
          </div>
          <p className="text-[11px] text-slate-400 leading-normal">
            Integer micro-dollar math (<code className="text-[#70e4bf]">$1 = 1,000,000 micros</code>) guarantees zero rounding drift across all runs.
          </p>
        </div>
      </div>
    </section>
  );
}
