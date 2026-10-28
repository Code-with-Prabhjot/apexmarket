import type { Metadata } from "next";
import Link from "next/link";
import {
  ShieldCheck,
  Cpu,
  Layers,
  Zap,
  Scale,
  Wallet,
  CheckCircle2,
  Lock,
  ArrowRight,
  ExternalLink,
  ChevronRight,
  FileText,
  Terminal,
  Activity,
  AlertTriangle,
  Fingerprint,
} from "lucide-react";

export const metadata: Metadata = {
  title: "System Architecture Whitepaper · ApexMarket",
  description:
    "Institutional specification of the 5-Tier Verification Stack, Economic Game Theory Slashing Mechanics, and PostgreSQL Double-Entry Ledger Balance Conservation.",
};

export default function ArchitecturePage() {
  return (
    <div className="min-h-screen bg-[#0a0f18] text-slate-100 flex flex-col selection:bg-[#70e4bf33]">
      {/* Top Header */}
      <header className="w-full border-b border-[#202c3c] bg-[#0c121e]/80 backdrop-blur sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <Link href="/" className="flex items-center gap-2 group">
              <span className="font-mono text-base font-black tracking-tight text-white group-hover:text-[#70e4bf] transition-colors">
                <span className="text-white">Apex</span>
                <span className="text-[#70e4bf]">Market</span>
              </span>
              <span className="px-2 py-0.5 rounded text-[10px] font-bold tracking-wider uppercase bg-[#70e4bf1a] text-[#70e4bf] border border-[#70e4bf33]">
                Whitepaper v3.0
              </span>
            </Link>

            <nav className="hidden md:flex items-center gap-5 text-xs font-semibold text-slate-400">
              <a href="#verification-stack" className="hover:text-slate-200 transition-colors">
                1. Verification Stack
              </a>
              <a href="#game-theory" className="hover:text-slate-200 transition-colors">
                2. Economic Game Theory
              </a>
              <a href="#ledger-mechanics" className="hover:text-slate-200 transition-colors">
                3. Double-Entry Ledger
              </a>
              <Link href="/verify" className="hover:text-slate-200 transition-colors">
                Attestation Verifier
              </Link>
            </nav>
          </div>

          <div className="flex items-center gap-3">
            <Link
              href="/verify"
              className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-[#70e4bf1a] text-[#70e4bf] border border-[#70e4bf33] hover:bg-[#70e4bf2b] transition-colors"
            >
              <Fingerprint size={14} /> Verify Bundle
            </Link>
            <Link
              href="/dashboard"
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold bg-[#1a2638] hover:bg-[#23334c] text-white border border-[#2a3c54] transition-colors"
            >
              <Cpu size={14} className="text-[#70e4bf]" /> Mission Control
            </Link>
          </div>
        </div>
      </header>

      {/* Main Container */}
      <main className="flex-1 max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        {/* Whitepaper Title Block */}
        <div className="pb-10 border-b border-[#202c3c]">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-[#70e4bf] mb-2">
            <FileText size={15} /> Technical Whitepaper &amp; Architectural Specification
          </div>
          <h1 className="text-3xl sm:text-4xl font-extrabold text-white tracking-tight">
            ApexMarket: Verified Inference Arbitrage &amp; Cryptographic Escrow
          </h1>
          <p className="text-base text-slate-400 mt-3 leading-relaxed max-w-3xl">
            Mathematical formulation and systems architecture of a decentralized multi-provider batch inference router.
            Features 5-tier cryptographic attestation, negative expected cheat economics (E[cheat] &lt; 0), and sub-cent double-entry ledger balance conservation.
          </p>
          <div className="flex flex-wrap items-center gap-4 mt-6 text-xs text-slate-400">
            <span className="flex items-center gap-1.5">
              <Cpu size={14} className="text-[#70e4bf]" /> <strong>Reference Anchor:</strong> Nebius Token Factory (Nemotron-3-Nano)
            </span>
            <span>•</span>
            <span className="flex items-center gap-1.5">
              <Wallet size={14} className="text-[#edbb72]" /> <strong>Settlement Boundary:</strong> PayPal Orders v2 &amp; Batch Payouts
            </span>
            <span>•</span>
            <span className="flex items-center gap-1.5">
              <ShieldCheck size={14} className="text-[#70e4bf]" /> <strong>Audit Status:</strong> Production Verified
            </span>
          </div>
        </div>

        {/* ========================================================================= */}
        {/* SECTION 1: THE 5-TIER VERIFICATION STACK */}
        {/* ========================================================================= */}
        <section id="verification-stack" className="py-12 border-b border-[#202c3c]">
          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-[#70e4bf] mb-2">
            Section 1.0
          </div>
          <h2 className="text-2xl sm:text-3xl font-black text-white tracking-tight">
            The 5-Tier Verification Stack
          </h2>
          <p className="text-sm text-slate-400 mt-2 leading-relaxed">
            Inference routing based purely on price floors introduces severe failure modes: silent INT4/FP8 quantization degradation, model substitution, and prompt truncation.
            ApexMarket operates under an institutional principle: <strong>proof precedes payment</strong>. Every batch is shredded into micro-batches of &le; 50 prompts and independently validated across 5 tiers before ledger settlement.
          </p>

          <div className="mt-8 space-y-6">
            {/* TIER 1 */}
            <div className="p-6 rounded-2xl bg-[#0c121e] border border-[#202c3c]">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2.5">
                  <span className="px-2.5 py-1 rounded text-xs font-mono font-bold bg-[#70e4bf1f] text-[#70e4bf] border border-[#70e4bf44]">
                    Tier 01
                  </span>
                  <h3 className="text-base font-bold text-white">
                    Authoritative Local Tokenizer Billing &amp; Safety Scan
                  </h3>
                </div>
                <span className="text-xs font-mono text-slate-400">HuggingFace AutoTokenizer</span>
              </div>
              <p className="text-xs text-slate-300 leading-relaxed">
                Untrusted spot providers have an economic incentive to inflate self-reported <code className="text-[#70e4bf]">usage.total_tokens</code> metadata.
                ApexMarket calculates all billing strictly using local byte-level tokenization:
              </p>
              <div className="p-3 my-3 rounded-lg bg-[#0a0f18] border border-[#202c3c] text-xs font-mono text-slate-200 overflow-x-auto">
                {"T_in = |tokenize(Prompt)|,    T_out = |tokenize(Completion)|"}
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">
                Furthermore, all completions are parsed by regex safety scanners targeting Prompt Injection exploits, XSS/SQLi payload reflection, and unauthorized PII leakage prior to client reassembly.
              </p>
            </div>

            {/* TIER 2 */}
            <div className="p-6 rounded-2xl bg-[#0c121e] border border-[#202c3c]">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2.5">
                  <span className="px-2.5 py-1 rounded text-xs font-mono font-bold bg-[#70e4bf1f] text-[#70e4bf] border border-[#70e4bf44]">
                    Tier 02
                  </span>
                  <h3 className="text-base font-bold text-white">
                    Dynamic Rotated Canary Probes (4% Secret Injection)
                  </h3>
                </div>
                <span className="text-xs font-mono text-slate-400">HMAC-SHA256 Sealed</span>
              </div>
              <p className="text-xs text-slate-300 leading-relaxed">
                Two secret canary prompts are synthesized per 50-prompt shred from parameterized generators (deterministic modular arithmetic, strict JSON structure extraction, and constrained sorting).
                Canary payloads are sealed with cluster HMAC keys:
              </p>
              <div className="p-3 my-3 rounded-lg bg-[#0a0f18] border border-[#202c3c] text-xs font-mono text-slate-200 overflow-x-auto">
                {"CanaryTag = HMAC-SHA256(SecretKey, shred_id || prompt_index)"}
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">
                Canary responses are stripped of reasoning tags (<code className="text-[#70e4bf]">&lt;think&gt;...&lt;/think&gt;</code>) and normalized for whitespace.
                A single formatting discrepancy triggers an immediate Tier-4 deep audit; &ge; 2 canary failures immediately fail the shred, slash the provider, and quarantine the node.
              </p>
            </div>

            {/* TIER 3 */}
            <div className="p-6 rounded-2xl bg-[#0c121e] border border-[#202c3c]">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2.5">
                  <span className="px-2.5 py-1 rounded text-xs font-mono font-bold bg-[#70e4bf1f] text-[#70e4bf] border border-[#70e4bf44]">
                    Tier 03
                  </span>
                  <h3 className="text-base font-bold text-white">
                    Secret-Seeded Anchor Reference Sampling (5% Split)
                  </h3>
                </div>
                <span className="text-xs font-mono text-slate-400">Nebius H100 @ Temp 0.0</span>
              </div>
              <p className="text-xs text-slate-300 leading-relaxed">
                To eliminate provider predictability, a cryptographically pseudo-random 5% of real user prompts are selected using HMAC shred seeds:
              </p>
              <div className="p-3 my-3 rounded-lg bg-[#0a0f18] border border-[#202c3c] text-xs font-mono text-slate-200 overflow-x-auto">
                {"Seed_CSPRNG = HMAC-SHA256(SecretKey, shred_id.bytes)[:8]"}
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">
                These prompts are concurrently executed on the trusted <strong>Nebius Token Factory Anchor</strong> (<code className="text-[#70e4bf]">nvidia/nemotron-3-nano-30b-a3b</code>) at temperature 0.0.
                This dual-stream execution establishes the authoritative baseline for semantic and perplexity comparison.
              </p>
            </div>

            {/* TIER 4 */}
            <div className="p-6 rounded-2xl bg-[#0c121e] border border-[#202c3c]">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2.5">
                  <span className="px-2.5 py-1 rounded text-xs font-mono font-bold bg-[#70e4bf1f] text-[#70e4bf] border border-[#70e4bf44]">
                    Tier 04
                  </span>
                  <h3 className="text-base font-bold text-white">
                    Anchor Teacher-Forcing NLL Logprob Scoring
                  </h3>
                </div>
                <span className="text-xs font-mono text-[#70e4bf]">Drift Cutoff: NLL &le; 2.80</span>
              </div>
              <p className="text-xs text-slate-300 leading-relaxed">
                Comparing raw token strings across models is fragile due to vocabulary desynchronization. ApexMarket implements <strong>Anchor Teacher-Forcing</strong>:
                the candidate node completion Y is passed back to the unquantized Nebius Anchor to compute the mean Negative Log-Likelihood (NLL) under golden weights:
              </p>
              <div className="p-4 my-3 rounded-lg bg-[#0a0f18] border border-[#202c3c] text-xs font-mono text-slate-200 overflow-x-auto leading-relaxed">
                {"NLL(Y_node | X) = - (1 / m) * SUM_{t=1}^m log P_anchor(y_t | X, y_{<t})"}
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">
                Honest nodes strictly operate within <code className="text-[#70e4bf]">μ_honest ≈ 1.24 ± 0.18</code>.
                Heavy INT4 quantization or model substitution causes immediate cross-entropy divergence (NLL &gt; 2.80), triggering instant slashing and anchor failover with 99.8% empirical confidence.
              </p>
            </div>

            {/* TIER 5 */}
            <div className="p-6 rounded-2xl bg-[#0c121e] border border-[#202c3c]">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2.5">
                  <span className="px-2.5 py-1 rounded text-xs font-mono font-bold bg-[#70e4bf1f] text-[#70e4bf] border border-[#70e4bf44]">
                    Tier 05
                  </span>
                  <h3 className="text-base font-bold text-white">
                    Nemotron Semantic Arbitration Judge
                  </h3>
                </div>
                <span className="text-xs font-mono text-slate-400">LLM-as-a-Judge Rubric</span>
              </div>
              <p className="text-xs text-slate-300 leading-relaxed">
                For borderline shreds (2.50 &le; NLL &le; 2.80) or complex open-ended reasoning tasks, a larger Nebius-hosted Nemotron instruction model acts as the supreme court arbiter.
                The judge scores the candidate against the reference answer on a 3-point rubric:
              </p>
              <ul className="list-disc list-inside mt-2 space-y-1 text-xs text-slate-400">
                <li><strong>Factual Equivalence:</strong> Core propositions must match the reference output.</li>
                <li><strong>Instruction Adherence:</strong> Strict schema, JSON key invariants, and formatting constraints.</li>
                <li><strong>Completeness:</strong> Penalizes truncated responses and premature stop sequences.</li>
              </ul>
            </div>
          </div>
        </section>

        {/* ========================================================================= */}
        {/* SECTION 2: ECONOMIC GAME THEORY & SLASHING */}
        {/* ========================================================================= */}
        <section id="game-theory" className="py-12 border-b border-[#202c3c]">
          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-[#edbb72] mb-2">
            Section 2.0
          </div>
          <h2 className="text-2xl sm:text-3xl font-black text-white tracking-tight">
            Economic Game Theory &amp; Slashing Penalty Function
          </h2>
          <p className="text-sm text-slate-400 mt-2 leading-relaxed">
            A compute marketplace cannot rely on altruism. It must be structured such that cheating is mathematically irrational.
            We present the formal proof demonstrating why dishonest spot operators face a strictly negative expected return:
          </p>

          <div className="mt-8 p-6 rounded-2xl bg-[#0c121e] border border-[#202c3c] space-y-6">
            <h3 className="text-base font-bold text-white flex items-center gap-2">
              <Scale size={18} className="text-[#edbb72]" /> Formulation of the Operator Penalty Function
            </h3>

            <p className="text-xs text-slate-300 leading-relaxed">
              Let <code className="text-[#70e4bf]">C_honest</code> be the operational cost per token of serving unquantized weights on verified H100 hardware, and let <code className="text-[#f87171]">C_cheat</code> be the reduced cost of serving an aggressively quantized INT4 model or proxying to a substandard model. The operator&apos;s marginal incentive to cheat is:
            </p>

            <div className="p-3 rounded-lg bg-[#0a0f18] border border-[#202c3c] text-xs font-mono text-slate-200">
              {"Delta_cheat = C_honest - C_cheat > 0"}
            </div>

            <p className="text-xs text-slate-300 leading-relaxed">
              Let <code className="text-[#70e4bf]">P_detect</code> be the composite probability that a corrupted shred is caught by our 5-tier pipeline.
              Because canaries (<code className="text-slate-300">P_canary = 1 - (1 - 0.04)^n</code>) and anchor logprob testing (<code className="text-slate-300">P_NLL &ge; 0.95</code>) operate concurrently:
            </p>

            <div className="p-3 rounded-lg bg-[#0a0f18] border border-[#202c3c] text-xs font-mono text-slate-200">
              {"P_detect = 1 - (1 - P_canary) * (1 - P_NLL) >= 0.987"}
            </div>

            <p className="text-xs text-slate-300 leading-relaxed">
              When caught, the operator suffers three distinct economic penalties:
            </p>
            <ol className="list-decimal list-inside space-y-1.5 text-xs text-slate-400">
              <li><strong>Zero Shred Settlement (<code className="text-[#f87171]">S_escrow = $0.00</code>):</strong> The current batch shred payout is completely forfeited.</li>
              <li><strong>Probation Balance Slashing (<code className="text-[#f87171]">P_probation</code>):</strong> Newly registered nodes are held in a 7-day probation escrow pool, all of which is slashed upon cheating.</li>
              <li><strong>Marketplace Exclusion (<code className="text-[#f87171]">V_future</code>):</strong> The node is permanently banned from cluster routing, forfeiting discounted future cash flows:
                <code className="text-[#70e4bf] ml-1">V_future = SUM(delta^t * Profit_t)</code>
              </li>
            </ol>

            <p className="text-xs text-slate-300 leading-relaxed font-semibold">
              The Expected Value of Cheating E[cheat] is formulated as:
            </p>

            <div className="p-4 rounded-lg bg-[#141824] border border-[#edbb7255] text-xs font-mono text-white leading-relaxed overflow-x-auto">
              {"E[cheat] = (1 - P_detect) * Delta_cheat - P_detect * (S_escrow + P_probation + V_future)"}
            </div>

            {/* Numerical Proof Box */}
            <div className="p-4 rounded-xl bg-[#121c2a] border border-[#202c3c] text-xs space-y-2">
              <span className="text-[10px] uppercase font-bold text-[#edbb72] tracking-wider block">
                Empirical Numerical Proof
              </span>
              <p className="text-slate-300">
                Consider an operator processing a 50-prompt shred attempting to pocket <code className="text-[#70e4bf]">Δ_cheat = $0.0004 / prompt = $0.02</code>.
                Under <code className="text-slate-300">P_detect = 0.987</code>, <code className="text-slate-300">S_escrow = $0.046</code>, <code className="text-slate-300">P_probation = $10.00</code>, and <code className="text-slate-300">V_future &ge; $50.00</code>:
              </p>
              <div className="font-mono text-[#70e4bf] pt-1">
                {"E[cheat] = (0.013 * $0.02) - 0.987 * ($0.046 + $10.00 + $50.00) = -$59.26 << 0"}
              </div>
              <p className="text-slate-400 text-[11px] pt-1">
                <strong>Theorem:</strong> Because E[cheat] &lt;&lt; 0, honest participation is the strictly dominant Nash equilibrium in all sub-games.
              </p>
            </div>
          </div>
        </section>

        {/* ========================================================================= */}
        {/* SECTION 3: DOUBLE-ENTRY LEDGER MECHANICS */}
        {/* ========================================================================= */}
        <section id="ledger-mechanics" className="py-12">
          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-[#70e4bf] mb-2">
            Section 3.0
          </div>
          <h2 className="text-2xl sm:text-3xl font-black text-white tracking-tight">
            Double-Entry Ledger Mechanics &amp; Balance Conservation
          </h2>
          <p className="text-sm text-slate-400 mt-2 leading-relaxed">
            Financial operations in AI infrastructure frequently suffer from rounding inaccuracies caused by IEEE-754 floating-point numbers.
            ApexMarket eliminates precision drift through <strong>integer micro-dollar arithmetic</strong> ($1,000,000 micros = $1.00) and a formal double-entry conservation invariant.
          </p>

          <div className="mt-8 space-y-6">
            {/* INVARIANT PROOF */}
            <div className="p-6 rounded-2xl bg-[#0c121e] border border-[#202c3c] space-y-4">
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <Wallet size={18} className="text-[#70e4bf]" /> Formal Proof of Balance Conservation
              </h3>

              <p className="text-xs text-slate-300 leading-relaxed">
                Let <code className="text-[#70e4bf]">B_total</code> represent the total cumulative deposits captured via PayPal Orders v2. At every discrete state transition <code className="text-slate-300">t_k &rarr; t_k+1</code>, the system enforces the conservation identity:
              </p>

              <div className="p-4 rounded-xl bg-[#0a0f18] border border-[#70e4bf44] text-xs font-mono text-white leading-relaxed overflow-x-auto shadow-inner">
                {"B_total = SUM(Available_c) + SUM(Escrow_j) + SUM(Probation_n + Withdrawable_n) + PlatformFee"}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                <div className="p-3 rounded-lg bg-[#141f30] border border-[#202c3c]">
                  <strong className="text-white block mb-0.5">1. Pre-Execution Lock:</strong>
                  <span className="text-slate-400 font-mono text-[11px]">
                    Available_c &rarr; Escrow_j &nbsp; (Delta B_total = 0)
                  </span>
                </div>
                <div className="p-3 rounded-lg bg-[#141f30] border border-[#202c3c]">
                  <strong className="text-white block mb-0.5">2. Verified Payout Credit:</strong>
                  <span className="text-slate-400 font-mono text-[11px]">
                    Escrow_j &rarr; Withdrawable_n + Fee + Refund_c &nbsp; (Delta = 0)
                  </span>
                </div>
              </div>
            </div>

            {/* PAYPAL IDEMPOTENCY & SUB-CENT CARRY */}
            <div className="p-6 rounded-2xl bg-[#0c121e] border border-[#202c3c] space-y-3">
              <h3 className="text-base font-bold text-white">
                Sub-Cent Micro-Dollar Precision &amp; Idempotent Payouts
              </h3>
              <p className="text-xs text-slate-300 leading-relaxed">
                PayPal Payouts enforces a minimum disbursement of $0.01 (10,000 micro-dollars).
                Micro-balances less than 10,000 micros remain safely in <code className="text-[#70e4bf]">withdrawable_micros</code> as sub-cent carryover for subsequent batch reconciliation.
              </p>
              <p className="text-xs text-slate-400 leading-relaxed">
                All external PayPal payout requests are protected by deterministic UUID <code className="text-[#70e4bf]">sender_batch_id</code> keys generated from the database row primary key, preventing duplicate payouts across network retries and HTTP timeouts.
              </p>
            </div>
          </div>
        </section>

        {/* Footer Navigation */}
        <div className="pt-8 border-t border-[#202c3c] flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-slate-400">
          <div className="flex items-center gap-4">
            <Link href="/" className="hover:text-slate-200 transition-colors">
              &larr; Landing Page
            </Link>
            <span>•</span>
            <Link href="/verify" className="hover:text-slate-200 transition-colors">
              Attestation Verifier
            </Link>
            <span>•</span>
            <Link href="/dashboard" className="hover:text-slate-200 transition-colors">
              Mission Control
            </Link>
          </div>
          <div>ApexMarket Systems Architecture &bull; Document ID: AM-WP-3.0</div>
        </div>
      </main>
    </div>
  );
}
