"use client";

import React, { useState } from "react";
import Link from "next/link";
import {
  Scale,
  TrendingDown,
  CheckCircle2,
  Clock,
  ArrowRight,
  ShieldCheck,
  Zap,
  Cpu,
  Sparkles,
  Info,
} from "lucide-react";

export interface ModelPricingOption {
  id: string;
  name: string;
  tag: string;
  onDemandPricePer1M: number; // in USD
  providerAnchor: string;
}

export const COMPARATOR_MODELS: ModelPricingOption[] = [
  {
    id: "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
    name: "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
    tag: "Nebius Token Factory Anchor",
    onDemandPricePer1M: 0.30,
    providerAnchor: "Nebius H100 Token Factory (Unquantized)",
  },
  {
    id: "meta-llama/Llama-3.1-8B-Instruct",
    name: "meta-llama/Llama-3.1-8B-Instruct",
    tag: "Community Spot Swarm Model",
    onDemandPricePer1M: 0.25,
    providerAnchor: "RunPod Spot + Nebius Failover",
  },
  {
    id: "mistralai/Mistral-NeMo-12B-Instruct",
    name: "mistralai/Mistral-NeMo-12B-Instruct",
    tag: "Enterprise Reasoning Baseline",
    onDemandPricePer1M: 0.35,
    providerAnchor: "Multi-Provider Hybrid Pool",
  },
];

export default function EconomicCalculator() {
  const [selectedModelId, setSelectedModelId] = useState<string>(COMPARATOR_MODELS[0].id);
  const [monthlyTokens, setMonthlyTokens] = useState<number>(2_500_000); // 2.5M tokens default

  const activeModel =
    COMPARATOR_MODELS.find((m) => m.id === selectedModelId) || COMPARATOR_MODELS[0];

  // Mathematical pricing breakdown
  const millionsTokens = monthlyTokens / 1_000_000;
  
  // 1. On-Demand Single Provider (Retail Pricing)
  const onDemandEffectivePer1M = activeModel.onDemandPricePer1M;
  const onDemandMonthlyCost = millionsTokens * onDemandEffectivePer1M;
  const onDemandAnnualCost = onDemandMonthlyCost * 12;

  // 2. Batch API Baseline (Standard 50% discount with 24-hour turnaround delay)
  const batchApiEffectivePer1M = activeModel.onDemandPricePer1M * 0.50;
  const batchApiMonthlyCost = millionsTokens * batchApiEffectivePer1M;
  const batchApiAnnualCost = batchApiMonthlyCost * 12;

  // 3. ApexMarket Hybrid (Empirical 32.18% net savings vs on-demand + real-time execution + full 9% audit overhead)
  const savingsPct = 32.18;
  const apexEffectivePer1M = activeModel.onDemandPricePer1M * (1 - savingsPct / 100);
  const apexMonthlyCost = millionsTokens * apexEffectivePer1M;
  const apexAnnualCost = apexMonthlyCost * 12;

  // Annual Dollar Savings vs On-Demand
  const annualDollarSavings = onDemandAnnualCost - apexAnnualCost;
  const monthlyDollarSavings = onDemandMonthlyCost - apexMonthlyCost;

  // Volume Presets
  const presets = [
    { label: "100k", value: 100_000 },
    { label: "1M", value: 1_000_000 },
    { label: "5M", value: 5_000_000 },
    { label: "10M", value: 10_000_000 },
  ];

  return (
    <div className="w-full rounded-2xl bg-[#0c121e] border border-[#202c3c] overflow-hidden shadow-2xl text-slate-100">
      {/* Header & Controls */}
      <div className="p-6 sm:p-8 bg-[#0e1624] border-b border-[#202c3c] flex flex-col md:flex-row md:items-end justify-between gap-6">
        <div className="space-y-2 flex-1">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-[#70e4bf]">
            <Scale size={16} /> Multi-Model Economic Comparator
          </div>
          <h3 className="text-xl sm:text-2xl font-black text-white tracking-tight">
            Arbitrage Cost Matrix vs Hyperscaler Menus
          </h3>
          <p className="text-xs sm:text-sm text-slate-400 max-w-2xl">
            Calculates empirical savings across open-weight architectures, accounting for the 9% verification audit overhead while delivering real-time streaming instead of 24-hour cold batch queues.
          </p>
        </div>

        {/* Model Selector Dropdown */}
        <div className="flex flex-col gap-1.5 w-full md:w-80">
          <label htmlFor="model-select" className="text-xs font-semibold text-slate-300">
            Target Model Architecture:
          </label>
          <div className="relative">
            <select
              id="model-select"
              value={selectedModelId}
              onChange={(e) => setSelectedModelId(e.target.value)}
              className="w-full px-3 py-2 text-xs font-mono bg-[#141f30] border border-[#25364c] rounded-xl text-white focus:outline-none focus:border-[#70e4bf] focus:ring-1 focus:ring-[#70e4bf] appearance-none pr-8 cursor-pointer"
            >
              {COMPARATOR_MODELS.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name} ({m.tag})
                </option>
              ))}
            </select>
            <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-2.5 text-slate-400">
              ▼
            </div>
          </div>
          <span className="text-[10px] text-slate-400 flex items-center gap-1">
            <Cpu size={12} className="text-[#70e4bf]" /> {activeModel.providerAnchor}
          </span>
        </div>
      </div>

      {/* Volume Slider Section */}
      <div className="p-6 sm:p-8 border-b border-[#202c3c] bg-[#090e18]">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-3">
          <div>
            <label htmlFor="token-slider" className="text-xs font-bold uppercase tracking-wider text-slate-300">
              Monthly Batch Volume:
            </label>
            <div className="text-2xl font-black text-white font-mono mt-0.5">
              {monthlyTokens.toLocaleString()} <span className="text-sm font-normal text-slate-400">tokens / month</span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {presets.map((p) => (
              <button
                key={p.value}
                onClick={() => setMonthlyTokens(p.value)}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold font-mono transition-all ${
                  monthlyTokens === p.value
                    ? "bg-[#70e4bf] text-black font-bold shadow-md shadow-[#70e4bf33]"
                    : "bg-[#141f30] text-slate-300 border border-[#25364c] hover:bg-[#1a293c]"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>

        <input
          id="token-slider"
          type="range"
          min="10000"
          max="10000000"
          step="50000"
          value={monthlyTokens}
          onChange={(e) => setMonthlyTokens(Number(e.target.value))}
          className="w-full h-2 bg-[#1b2738] rounded-lg appearance-none cursor-pointer accent-[#70e4bf]"
        />

        <div className="flex justify-between text-[10px] font-mono text-slate-400 mt-2">
          <span>10k tok</span>
          <span>2.5M tok</span>
          <span>5.0M tok</span>
          <span>7.5M tok</span>
          <span>10.0M tokens/mo</span>
        </div>
      </div>

      {/* 3-Column Comparative Output Breakdown */}
      <div className="grid grid-cols-1 md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-[#202c3c] bg-[#0c121e]">
        {/* COLUMN 1: ON-DEMAND SINGLE PROVIDER */}
        <div className="p-6 sm:p-8 flex flex-col justify-between space-y-6">
          <div className="space-y-3">
            <span className="px-2.5 py-1 rounded text-[10px] font-bold uppercase tracking-wider bg-[#1a2638] text-slate-300 border border-[#2a3c54]">
              Column 1: Hyperscaler Retail
            </span>
            <h4 className="text-base font-bold text-white">On-Demand Single Provider</h4>
            <p className="text-xs text-slate-400 leading-relaxed">
              Standard hyperscaler pay-as-you-go API rate. Immediate execution with zero verification.
            </p>

            <div className="pt-2">
              <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">Effective Rate</span>
              <div className="text-lg font-black text-slate-200 font-mono mt-0.5">
                ${onDemandEffectivePer1M.toFixed(4)}{" "}
                <span className="text-xs font-normal text-slate-400">/ 1M tokens</span>
              </div>
            </div>

            <div className="p-4 rounded-xl bg-[#101826] border border-[#202c3c]">
              <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">Annual Cost</span>
              <div className="text-2xl font-black text-slate-200 font-mono mt-0.5">
                ${onDemandAnnualCost.toFixed(2)}
              </div>
              <span className="text-[11px] font-mono text-slate-400 block mt-0.5">
                ${onDemandMonthlyCost.toFixed(2)} / month
              </span>
            </div>
          </div>

          <ul className="space-y-2 text-xs text-slate-400 border-t border-[#202c3c] pt-4">
            <li className="flex items-center gap-2">
              <span className="text-slate-500">•</span>
              <span>Single provider lock-in</span>
            </li>
            <li className="flex items-center gap-2">
              <span className="text-slate-500">•</span>
              <span>0% Verification / No canary audit</span>
            </li>
            <li className="flex items-center gap-2">
              <span className="text-slate-500">•</span>
              <span>100% retail menu cost</span>
            </li>
          </ul>
        </div>

        {/* COLUMN 2: BATCH API BASELINE */}
        <div className="p-6 sm:p-8 flex flex-col justify-between space-y-6">
          <div className="space-y-3">
            <span className="px-2.5 py-1 rounded text-[10px] font-bold uppercase tracking-wider bg-[#edbb721a] text-[#edbb72] border border-[#edbb7244]">
              Column 2: 50% Batch API
            </span>
            <h4 className="text-base font-bold text-white">Batch API Baseline</h4>
            <p className="text-xs text-slate-400 leading-relaxed">
              Standard 50% discount offered by commercial providers, constrained by 24-hour SLA delays.
            </p>

            <div className="pt-2">
              <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">Effective Rate</span>
              <div className="text-lg font-black text-slate-200 font-mono mt-0.5">
                ${batchApiEffectivePer1M.toFixed(4)}{" "}
                <span className="text-xs font-normal text-slate-400">/ 1M tokens</span>
              </div>
            </div>

            <div className="p-4 rounded-xl bg-[#101826] border border-[#202c3c]">
              <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">Annual Cost</span>
              <div className="text-2xl font-black text-slate-200 font-mono mt-0.5">
                ${batchApiAnnualCost.toFixed(2)}
              </div>
              <span className="text-[11px] font-mono text-slate-400 block mt-0.5">
                ${batchApiMonthlyCost.toFixed(2)} / month
              </span>
            </div>
          </div>

          <ul className="space-y-2 text-xs text-slate-400 border-t border-[#202c3c] pt-4">
            <li className="flex items-center gap-2">
              <Clock size={14} className="text-[#edbb72]" />
              <span className="text-amber-200/90 font-medium">24-hour turnaround delay</span>
            </li>
            <li className="flex items-center gap-2">
              <span className="text-slate-500">•</span>
              <span>Offline queue with zero latency SLA</span>
            </li>
            <li className="flex items-center gap-2">
              <span className="text-slate-500">•</span>
              <span>Silent quantization risks unmitigated</span>
            </li>
          </ul>
        </div>

        {/* COLUMN 3: APEXMARKET HYBRID */}
        <div className="p-6 sm:p-8 flex flex-col justify-between space-y-6 bg-gradient-to-b from-[#0e1d24] via-[#0c181f] to-[#0c121e]">
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="px-2.5 py-1 rounded text-[10px] font-bold uppercase tracking-wider bg-[#70e4bf] text-black">
                Column 3: ApexMarket Hybrid
              </span>
              <span className="text-[11px] font-mono font-bold text-[#70e4bf]">
                32.18% NET SAVINGS
              </span>
            </div>
            <h4 className="text-base font-bold text-white flex items-center gap-1.5">
              <Sparkles size={16} className="text-[#70e4bf]" /> ApexMarket Verified
            </h4>
            <p className="text-xs text-slate-300 leading-relaxed">
              Empirical cost arbitrage combining RunPod spot nodes and Nebius reference anchor with full 9% audit overhead included.
            </p>

            <div className="pt-2">
              <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">Effective Rate</span>
              <div className="text-lg font-black text-[#70e4bf] font-mono mt-0.5">
                ${apexEffectivePer1M.toFixed(4)}{" "}
                <span className="text-xs font-normal text-slate-400">/ 1M tokens</span>
              </div>
            </div>

            <div className="p-4 rounded-xl bg-[#102422] border border-[#70e4bf55] shadow-lg shadow-[#70e4bf10]">
              <span className="text-[10px] uppercase font-bold text-[#70e4bf] tracking-wider">Annual Cost</span>
              <div className="text-2xl font-black text-white font-mono mt-0.5">
                ${apexAnnualCost.toFixed(2)}
              </div>
              <span className="text-[11px] font-mono text-[#70e4bf] block mt-0.5">
                ${apexMonthlyCost.toFixed(2)} / month
              </span>
            </div>
          </div>

          <ul className="space-y-2 text-xs text-slate-300 border-t border-[#70e4bf33] pt-4">
            <li className="flex items-center gap-2">
              <CheckCircle2 size={14} className="text-[#70e4bf]" />
              <span className="font-semibold text-white">Real-Time Execution (&lt;120ms TTFT)</span>
            </li>
            <li className="flex items-center gap-2">
              <CheckCircle2 size={14} className="text-[#70e4bf]" />
              <span>5-Tier Proof Before Payment Audit</span>
            </li>
            <li className="flex items-center gap-2">
              <CheckCircle2 size={14} className="text-[#70e4bf]" />
              <span>Nebius Nemotron-3-Nano Anchor</span>
            </li>
          </ul>
        </div>
      </div>

      {/* Dynamic Savings Summary Banner */}
      <div className="p-6 bg-[#0a141b] border-t border-[#202c3c] flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <span className="text-xs font-bold uppercase tracking-wider text-[#70e4bf] flex items-center gap-1.5">
            <TrendingDown size={15} /> Verified Institutional Arbitrage
          </span>
          <div className="text-2xl sm:text-3xl font-black text-white font-mono mt-1 flex items-baseline gap-2">
            +${annualDollarSavings.toFixed(2)}
            <span className="text-xs font-normal text-slate-400">Annual Net Dollar Savings</span>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            Saves ${monthlyDollarSavings.toFixed(2)} / month while eliminating the 24-hour turnaround delay of Batch APIs.
          </p>
        </div>

        <Link
          href="/dashboard"
          className="px-5 py-3 rounded-xl text-xs font-bold bg-[#70e4bf] hover:bg-[#5cd4ad] text-black transition-all flex items-center justify-center gap-2 shadow-lg shadow-[#70e4bf22] shrink-0"
        >
          Launch Mission Control <ArrowRight size={15} />
        </Link>
      </div>
    </div>
  );
}
