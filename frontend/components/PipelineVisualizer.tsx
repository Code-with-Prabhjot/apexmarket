"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  Play,
  Pause,
  ChevronRight,
  ChevronLeft,
  RotateCcw,
  ShieldCheck,
  ShieldAlert,
  Cpu,
  Layers,
  Zap,
  Flame,
  CheckCircle2,
  ArrowRight,
  Lock,
  Wallet,
  Sparkles,
  Server,
  Activity,
  AlertOctagon,
  Scale,
  RefreshCw,
} from "lucide-react";

export interface PipelineVisualizerProps {
  initialStage?: number;
  autoPlay?: boolean;
}

export default function PipelineVisualizer({
  initialStage = 1,
  autoPlay = false,
}: PipelineVisualizerProps) {
  const [currentStage, setCurrentStage] = useState<number>(initialStage);
  const [isPlaying, setIsPlaying] = useState<boolean>(autoPlay);
  const [chaosDrift, setChaosDrift] = useState<boolean>(false);
  const [confidentialMode, setConfidentialMode] = useState<boolean>(false);
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  const stages = [
    {
      num: 1,
      title: "Batch Ingestion & Shredding",
      short: "Ingestion",
      desc: "50 raw enterprise prompts ingested, PII sanitized, and partitioned into deterministic micro-batches via offline HuggingFace AutoTokenizer.",
      badge: "50 Prompts · 5 Shreds",
    },
    {
      num: 2,
      title: "Capacity-Aware Greedy Routing",
      short: "Routing",
      desc: "Water-filling scheduler routes shreds across RunPod spot capacity, air-gapping confidential workloads 100% to the trusted Nebius Anchor.",
      badge: "Spot Swarm + Nebius Anchor",
    },
    {
      num: 3,
      title: "Active Canary Injection",
      short: "Canary Probes",
      desc: "4% secret challenge prompts injected with HMAC-SHA256 signatures to verify execution fidelity and detect prompt truncation.",
      badge: "4% HMAC-Sealed Canaries",
    },
    {
      num: 4,
      title: "INT4 Drift Detection & Quarantine",
      short: "Drift Audit",
      desc: "Anchor teacher-forcing computes cross-entropy logprobs. Quantized spot output exceeding NLL 2.80 is slashed and rerouted to Nebius.",
      badge: "NLL Logprob Audit",
    },
    {
      num: 5,
      title: "Deterministic Reassembly & Settlement",
      short: "Settlement",
      desc: "Outputs reassembled in original sequence. Double-entry ledger settles PayPal micro-dollar escrow with zero IEEE-754 rounding drift.",
      badge: "PayPal Micro-Dollar Escrow",
    },
  ];

  // Auto-play progression loop
  useEffect(() => {
    if (isPlaying) {
      timerRef.current = setInterval(() => {
        setCurrentStage((prev) => (prev >= 5 ? 1 : prev + 1));
      }, 4500);
    } else if (timerRef.current) {
      clearInterval(timerRef.current);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [isPlaying]);

  const handleNext = () => {
    setCurrentStage((prev) => (prev >= 5 ? 1 : prev + 1));
  };

  const handlePrev = () => {
    setCurrentStage((prev) => (prev <= 1 ? 5 : prev - 1));
  };

  return (
    <div className="w-full rounded-2xl bg-[#0c121e] border border-[#202c3c] overflow-hidden shadow-2xl text-slate-100">
      {/* Top Header & Playback Control Bar */}
      <div className="p-4 sm:p-5 bg-[#0e1624] border-b border-[#202c3c] flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-[#70e4bf] mb-1">
            <Activity size={15} /> 5-Tier Protected Batch Pipeline Simulator
          </div>
          <h3 className="text-lg sm:text-xl font-bold text-white flex items-center gap-2">
            Stage {currentStage}: {stages[currentStage - 1].title}
          </h3>
        </div>

        {/* Playback & Chaos Controller */}
        <div className="flex flex-wrap items-center gap-2.5">
          <button
            onClick={() => setIsPlaying(!isPlaying)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              isPlaying
                ? "bg-[#edbb7222] text-[#edbb72] border border-[#edbb7255]"
                : "bg-[#70e4bf1f] text-[#70e4bf] border border-[#70e4bf44] hover:bg-[#70e4bf33]"
            }`}
          >
            {isPlaying ? <Pause size={14} /> : <Play size={14} />}
            {isPlaying ? "Pause" : "Play Pipeline"}
          </button>

          <button
            onClick={handlePrev}
            className="p-1.5 rounded-lg text-slate-300 hover:text-white bg-[#162232] border border-[#202c3c] hover:bg-[#1a293c] transition-colors"
            title="Previous Stage"
          >
            <ChevronLeft size={16} />
          </button>

          <button
            onClick={handleNext}
            className="p-1.5 rounded-lg text-slate-300 hover:text-white bg-[#162232] border border-[#202c3c] hover:bg-[#1a293c] transition-colors"
            title="Next Stage"
          >
            <ChevronRight size={16} />
          </button>

          <div className="h-5 w-px bg-[#202c3c] mx-1" />

          {/* Chaos Drift Simulation Toggle */}
          <button
            onClick={() => {
              setChaosDrift(!chaosDrift);
              if (!chaosDrift && currentStage < 4) {
                setCurrentStage(4);
              }
            }}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              chaosDrift
                ? "bg-[#f871712a] text-[#f87171] border border-[#f8717166] shadow-lg shadow-[#f8717115]"
                : "bg-[#162232] text-slate-300 border border-[#202c3c] hover:text-[#f87171] hover:border-[#f8717144]"
            }`}
            title="Inject simulated quantization drift on RunPod spot nodes"
          >
            <Flame size={14} className={chaosDrift ? "animate-bounce text-[#f87171]" : ""} />
            {chaosDrift ? "Chaos Drift: ACTIVE" : "Simulate Chaos Drift"}
          </button>
        </div>
      </div>

      {/* Stepped Stage Indicator Tabs */}
      <div className="grid grid-cols-5 border-b border-[#202c3c] bg-[#0a0f18]">
        {stages.map((stage) => {
          const isActive = currentStage === stage.num;
          const isPassed = currentStage > stage.num;
          return (
            <button
              key={stage.num}
              onClick={() => {
                setCurrentStage(stage.num);
                setIsPlaying(false);
              }}
              className={`py-3 px-2 text-center transition-all relative flex flex-col items-center justify-center border-r last:border-r-0 border-[#202c3c] ${
                isActive
                  ? "bg-[#141f30] text-white"
                  : isPassed
                  ? "text-slate-400 hover:text-slate-200 hover:bg-[#0e1624]"
                  : "text-slate-500 hover:text-slate-300 hover:bg-[#0e1624]"
              }`}
            >
              <div className="flex items-center gap-1.5 mb-1">
                <span
                  className={`w-5 h-5 rounded-full text-[10px] font-bold flex items-center justify-center transition-all ${
                    isActive
                      ? "bg-[#70e4bf] text-black shadow-md shadow-[#70e4bf55]"
                      : isPassed
                      ? "bg-[#70e4bf33] text-[#70e4bf] border border-[#70e4bf55]"
                      : "bg-[#1a2638] text-slate-400"
                  }`}
                >
                  {isPassed ? "✓" : stage.num}
                </span>
                <span className="hidden sm:inline text-xs font-semibold">{stage.short}</span>
              </div>
              <span className="text-[10px] text-slate-400 hidden md:block truncate max-w-[120px]">
                {stage.badge}
              </span>
              {isActive && (
                <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-[#70e4bf] shadow-sm shadow-[#70e4bf]" />
              )}
            </button>
          );
        })}
      </div>

      {/* Interactive Simulation Display Canvas */}
      <div className="p-6 sm:p-8 min-h-[380px] flex flex-col justify-between bg-gradient-to-b from-[#0c121e] via-[#090d16] to-[#0a0f18] relative overflow-hidden">
        {/* Background Network Graphic Overlay */}
        <div className="absolute inset-0 opacity-10 pointer-events-none bg-[radial-gradient(#70e4bf_1px,transparent_1px)] [background-size:24px_24px]" />

        {/* Stage Content */}
        <div className="relative z-10">
          {/* STAGE 1: BATCH INGESTION */}
          {currentStage === 1 && (
            <div className="space-y-6">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 p-4 rounded-xl bg-[#141f30] border border-[#202c3c]">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-[#70e4bf1f] border border-[#70e4bf44] flex items-center justify-center text-[#70e4bf]">
                    <Layers size={20} />
                  </div>
                  <div>
                    <h4 className="text-sm font-bold text-white">Batch Ingestion Queue: 50 Prompts</h4>
                    <p className="text-xs text-slate-400">Offline HuggingFace AutoTokenizer · PII Redaction Active</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="px-2.5 py-1 rounded text-xs font-mono font-bold bg-[#70e4bf22] text-[#70e4bf] border border-[#70e4bf44]">
                    6,400 Tokens Tokenized
                  </span>
                </div>
              </div>

              {/* Shredding Representation Grid */}
              <div className="grid grid-cols-1 sm:grid-cols-5 gap-3">
                {[
                  { id: "Shred-01", prompts: "Prompts 00-09", tokens: "1,280 tok", status: "Ready" },
                  { id: "Shred-02", prompts: "Prompts 10-19", tokens: "1,280 tok", status: "Ready" },
                  { id: "Shred-03", prompts: "Prompts 20-29", tokens: "1,280 tok", status: "Ready" },
                  { id: "Shred-04", prompts: "Prompts 30-39", tokens: "1,280 tok", status: "Ready" },
                  { id: "Shred-05", prompts: "Prompts 40-49", tokens: "1,280 tok", status: "Ready" },
                ].map((s, idx) => (
                  <div
                    key={s.id}
                    className="p-3.5 rounded-xl bg-[#101826] border border-[#25364c] hover:border-[#70e4bf66] transition-all flex flex-col justify-between"
                  >
                    <div>
                      <div className="flex items-center justify-between text-xs font-bold text-white mb-1">
                        <span>{s.id}</span>
                        <span className="text-[10px] font-mono text-[#70e4bf]">{s.tokens}</span>
                      </div>
                      <p className="text-[11px] text-slate-400">{s.prompts}</p>
                    </div>
                    <div className="mt-3 pt-2 border-t border-[#1e2c3e] flex items-center justify-between text-[10px]">
                      <span className="text-slate-400">PII Clean</span>
                      <span className="text-[#70e4bf] font-semibold">10 Items</span>
                    </div>
                  </div>
                ))}
              </div>

              <div className="p-3 rounded-lg bg-[#0e1624] border border-[#202c3c] text-xs text-slate-400 flex items-center justify-between">
                <span>Deterministic token count: Authoritative local billing guarantees no provider usage inflation.</span>
                <span className="text-[#70e4bf] font-semibold">Step 1 of 5</span>
              </div>
            </div>
          )}

          {/* STAGE 2: CAPACITY-AWARE ROUTING */}
          {currentStage === 2 && (
            <div className="space-y-6">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 p-4 rounded-xl bg-[#141f30] border border-[#202c3c]">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-[#edbb721f] border border-[#edbb7244] flex items-center justify-center text-[#edbb72]">
                    <Zap size={20} />
                  </div>
                  <div>
                    <h4 className="text-sm font-bold text-white">Capacity-Aware Water-Filling Scheduler</h4>
                    <p className="text-xs text-slate-400">Routes to lowest effective cost while air-gapping confidential jobs</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setConfidentialMode(!confidentialMode)}
                    className={`px-3 py-1 rounded text-xs font-bold transition-all flex items-center gap-1.5 ${
                      confidentialMode
                        ? "bg-[#70e4bf22] text-[#70e4bf] border border-[#70e4bf55]"
                        : "bg-[#1a2638] text-slate-300 border border-[#2a3c54]"
                    }`}
                  >
                    <Lock size={12} />
                    {confidentialMode ? "Confidential: 100% Nebius Anchor" : "Public/Synthetic: Spot Swarm"}
                  </button>
                </div>
              </div>

              {/* Node Distribution Matrix */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div
                  className={`p-4 rounded-xl border transition-all ${
                    confidentialMode
                      ? "bg-[#0f1928] border-slate-700/50 opacity-60"
                      : "bg-[#101826] border-[#25364c]"
                  }`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-bold text-slate-200">RunPod Spot-Alpha</span>
                    <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-[#edbb7222] text-[#edbb72]">
                      $0.04 / 1M
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400 mb-3">520 tok/s · PCIe H100 spot capacity</p>
                  <div className="p-2.5 rounded bg-[#162232] border border-[#202c3c] text-xs font-mono">
                    <div className="text-slate-300 font-semibold mb-1">
                      {confidentialMode ? "0 Shreds (Air-Gapped)" : "Assigned: Shred-01 & Shred-02"}
                    </div>
                    <div className="text-[10px] text-slate-400">Concurrency: 2 / 10 slots</div>
                  </div>
                </div>

                <div
                  className={`p-4 rounded-xl border transition-all ${
                    confidentialMode
                      ? "bg-[#0f1928] border-slate-700/50 opacity-60"
                      : "bg-[#101826] border-[#25364c]"
                  }`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-bold text-slate-200">RunPod Spot-Beta</span>
                    <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-[#edbb7222] text-[#edbb72]">
                      $0.03 / 1M
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400 mb-3">480 tok/s · Community GPU spot pool</p>
                  <div className="p-2.5 rounded bg-[#162232] border border-[#202c3c] text-xs font-mono">
                    <div className="text-slate-300 font-semibold mb-1">
                      {confidentialMode ? "0 Shreds (Air-Gapped)" : "Assigned: Shred-03 & Shred-04"}
                    </div>
                    <div className="text-[10px] text-slate-400">Concurrency: 2 / 8 slots</div>
                  </div>
                </div>

                <div className="p-4 rounded-xl bg-[#0f211d] border border-[#70e4bf55] shadow-lg shadow-[#70e4bf10]">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-bold text-white flex items-center gap-1.5">
                      <Cpu size={14} className="text-[#70e4bf]" /> Nebius Token Factory
                    </span>
                    <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-[#70e4bf22] text-[#70e4bf]">
                      Trusted Anchor
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-300 mb-3">898 tok/s · Unquantized Reference Model</p>
                  <div className="p-2.5 rounded bg-[#122b24] border border-[#70e4bf33] text-xs font-mono">
                    <div className="text-[#70e4bf] font-semibold mb-1">
                      {confidentialMode ? "100% Routed (All 5 Shreds)" : "Assigned: Shred-05 + 5% CSPRNG Audit"}
                    </div>
                    <div className="text-[10px] text-slate-300">Air-Gap Protection: Active</div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* STAGE 3: ACTIVE CANARY INJECTION */}
          {currentStage === 3 && (
            <div className="space-y-6">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 p-4 rounded-xl bg-[#141f30] border border-[#202c3c]">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-[#70e4bf1f] border border-[#70e4bf44] flex items-center justify-center text-[#70e4bf]">
                    <ShieldCheck size={20} />
                  </div>
                  <div>
                    <h4 className="text-sm font-bold text-white">Active Canary Injection (4% Secret Probes)</h4>
                    <p className="text-xs text-slate-400">HMAC-signed synthetic challenges mixed secretly into micro-batches</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="px-2.5 py-1 rounded text-xs font-mono font-bold bg-[#70e4bf22] text-[#70e4bf] border border-[#70e4bf44]">
                    HMAC-SHA256 Signed
                  </span>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-4 rounded-xl bg-[#101826] border border-[#202c3c] flex flex-col justify-between">
                  <div>
                    <div className="flex items-center justify-between text-xs font-semibold text-white mb-2">
                      <span className="text-[#edbb72]">Canary Probe #1 (Deterministic Math)</span>
                      <span className="text-[10px] font-mono text-slate-400">Shred-02</span>
                    </div>
                    <div className="p-3 rounded-lg bg-[#0a0f18] border border-[#202c3c] text-xs font-mono text-slate-300">
                      <code>&quot;Evaluate: sum(primes_between(10, 30)) * 17&quot;</code>
                      <div className="mt-2 text-[11px] text-[#70e4bf]">
                        Expected Gold Answer: <code>1904</code>
                      </div>
                    </div>
                  </div>
                  <div className="mt-4 pt-3 border-t border-[#1e2c3e] flex items-center justify-between text-[11px]">
                    <span className="text-slate-400">Sealed Verification Tag:</span>
                    <span className="font-mono text-[#70e4bf]">hmac_e7d1a2f9...</span>
                  </div>
                </div>

                <div className="p-4 rounded-xl bg-[#101826] border border-[#202c3c] flex flex-col justify-between">
                  <div>
                    <div className="flex items-center justify-between text-xs font-semibold text-white mb-2">
                      <span className="text-[#edbb72]">Canary Probe #2 (JSON Key Invariant)</span>
                      <span className="text-[10px] font-mono text-slate-400">Shred-04</span>
                    </div>
                    <div className="p-3 rounded-lg bg-[#0a0f18] border border-[#202c3c] text-xs font-mono text-slate-300">
                      <code>&quot;Extract keys in strict schema: {'{e: 42, v: 99}'}&quot;</code>
                      <div className="mt-2 text-[11px] text-[#70e4bf]">
                        Expected Gold Answer: <code>{'{e: 42, v: 99}'}</code>
                      </div>
                    </div>
                  </div>
                  <div className="mt-4 pt-3 border-t border-[#1e2c3e] flex items-center justify-between text-[11px]">
                    <span className="text-slate-400">Sealed Verification Tag:</span>
                    <span className="font-mono text-[#70e4bf]">hmac_8bfa0411...</span>
                  </div>
                </div>
              </div>

              <div className="p-3 rounded-lg bg-[#0e1624] border border-[#202c3c] text-xs text-slate-400">
                Injected canaries appear indistinguishable from authentic user prompts, preventing compute nodes from selectively prioritizing audit tasks.
              </div>
            </div>
          )}

          {/* STAGE 4: INT4 DRIFT DETECTION & QUARANTINE */}
          {currentStage === 4 && (
            <div className="space-y-6">
              <div
                className={`flex flex-col sm:flex-row sm:items-center justify-between gap-2 p-4 rounded-xl border transition-all ${
                  chaosDrift
                    ? "bg-[#2d1216] border-[#f8717166]"
                    : "bg-[#141f30] border-[#202c3c]"
                }`}
              >
                <div className="flex items-center gap-3">
                  <div
                    className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                      chaosDrift
                        ? "bg-[#f871712a] border border-[#f87171] text-[#f87171]"
                        : "bg-[#70e4bf1f] border border-[#70e4bf44] text-[#70e4bf]"
                    }`}
                  >
                    {chaosDrift ? <AlertOctagon size={20} /> : <ShieldCheck size={20} />}
                  </div>
                  <div>
                    <h4 className="text-sm font-bold text-white">
                      {chaosDrift ? "Active Drift Detected: Spot Node Quarantined" : "Teacher-Forcing NLL Scoring"}
                    </h4>
                    <p className="text-xs text-slate-300">
                      Cross-entropy logprobs audited against Nebius reference model weights (NLL Threshold &le; 2.80)
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span
                    className={`px-2.5 py-1 rounded text-xs font-mono font-bold border ${
                      chaosDrift
                        ? "bg-[#f871712a] text-[#f87171] border-[#f8717166]"
                        : "bg-[#70e4bf22] text-[#70e4bf] border-[#70e4bf44]"
                    }`}
                  >
                    {chaosDrift ? "NLL = 3.42 (DRIFT)" : "NLL = 1.24 (PASS)"}
                  </span>
                </div>
              </div>

              {/* Drift & Failover Flow Visual */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div
                  className={`p-4 rounded-xl border transition-all ${
                    chaosDrift
                      ? "bg-[#1d1217] border-[#f8717188] shadow-lg shadow-[#f871711a]"
                      : "bg-[#101826] border-[#202c3c]"
                  }`}
                >
                  <div className="flex items-center justify-between text-xs font-bold mb-2">
                    <span className={chaosDrift ? "text-[#f87171]" : "text-slate-200"}>
                      RunPod Spot-Beta (Shred-04)
                    </span>
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] uppercase font-bold ${
                        chaosDrift ? "bg-[#f87171] text-black" : "bg-emerald-950 text-[#70e4bf]"
                      }`}
                    >
                      {chaosDrift ? "SLASHED · $0.00" : "HONEST · 100%"}
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400 mb-3">
                    {chaosDrift
                      ? "Severe perplexity spike detected. Node attempted silent INT4 model substitution."
                      : "Perplexity within honest distribution: μ + 1.2σ. Zero quantization anomalies."}
                  </p>
                  <div className="p-3 rounded bg-[#0a0f18] border border-[#202c3c] text-xs font-mono">
                    <div className="flex justify-between text-[11px] text-slate-400 mb-1">
                      <span>Measured NLL Score:</span>
                      <span className={chaosDrift ? "text-[#f87171] font-bold" : "text-[#70e4bf]"}>
                        {chaosDrift ? "3.42 (> 2.80 Cutoff)" : "1.24 (< 2.80 Cutoff)"}
                      </span>
                    </div>
                    <div className="flex justify-between text-[11px] text-slate-400">
                      <span>Payout Status:</span>
                      <span className={chaosDrift ? "text-red-400 font-bold" : "text-emerald-400"}>
                        {chaosDrift ? "Forfeited / Slashed" : "Approved for Ledger"}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Failover Arrow to Nebius */}
                <div className="p-4 rounded-xl bg-[#0f211d] border border-[#70e4bf55] flex flex-col justify-between shadow-lg shadow-[#70e4bf10]">
                  <div>
                    <div className="flex items-center justify-between text-xs font-bold text-white mb-2">
                      <span className="flex items-center gap-1.5 text-[#70e4bf]">
                        <Cpu size={14} /> Nebius Token Factory Anchor
                      </span>
                      <span className="px-2 py-0.5 rounded text-[10px] uppercase font-bold bg-[#70e4bf22] text-[#70e4bf]">
                        {chaosDrift ? "Failover Target" : "Reference Baseline"}
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-300 mb-3">
                      {chaosDrift
                        ? "Unverified Shred-04 automatically failovers to Nebius Anchor at temperature 0.0 with zero data loss."
                        : "Reference golden model unquantized on Nebius H100 GPU cluster."}
                    </p>
                  </div>
                  <div className="p-3 rounded bg-[#122b24] border border-[#70e4bf33] text-xs font-mono">
                    <div className="flex items-center gap-2 text-[#70e4bf]">
                      <ArrowRight size={14} />
                      <span className="font-semibold">
                        {chaosDrift ? "Failover executed in 410ms · Full re-audit" : "Anchor standby · 0 Failovers"}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* STAGE 5: DETERMINISTIC REASSEMBLY & SETTLEMENT */}
          {currentStage === 5 && (
            <div className="space-y-6">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 p-4 rounded-xl bg-[#141f30] border border-[#202c3c]">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-[#70e4bf1f] border border-[#70e4bf44] flex items-center justify-center text-[#70e4bf]">
                    <Wallet size={20} />
                  </div>
                  <div>
                    <h4 className="text-sm font-bold text-white">Deterministic Reassembly & PayPal Settlement</h4>
                    <p className="text-xs text-slate-400">Prompts restored in original order · Micro-dollar balance conserved</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="px-2.5 py-1 rounded text-xs font-mono font-bold bg-[#70e4bf22] text-[#70e4bf] border border-[#70e4bf44]">
                    $0.046150 Settled
                  </span>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div className="p-4 rounded-xl bg-[#101826] border border-[#202c3c]">
                  <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">Reassembly Order</span>
                  <div className="text-base font-black text-white mt-1">50 / 50 Prompts</div>
                  <p className="text-[11px] text-slate-400 mt-1">Strict prompt_index [0..49] restored.</p>
                </div>

                <div className="p-4 rounded-xl bg-[#101826] border border-[#202c3c]">
                  <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">Net Client Savings</span>
                  <div className="text-base font-black text-[#70e4bf] mt-1">32.18% Savings</div>
                  <p className="text-[11px] text-slate-400 mt-1">Full 9% audit overhead accounted.</p>
                </div>

                <div className="p-4 rounded-xl bg-[#101826] border border-[#202c3c]">
                  <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">Settlement Ledger</span>
                  <div className="text-base font-black text-[#edbb72] mt-1">PayPal Batch Paid</div>
                  <p className="text-[11px] text-slate-400 mt-1">UUID idempotency · Zero double-spend.</p>
                </div>
              </div>

              <div className="p-4 rounded-xl bg-[#0f211d] border border-[#70e4bf44] flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
                <div className="flex items-center gap-2.5 text-slate-200">
                  <CheckCircle2 size={18} className="text-[#70e4bf]" />
                  <span>
                    Attestation Certificate exported: <code className="text-[#70e4bf]">apexmarket-attestation-0428.json</code>
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-[#70e4bf] text-black">
                    JOB COMPLETED
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Bottom Explanatory Caption */}
        <div className="mt-8 pt-4 border-t border-[#202c3c] flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs text-slate-400">
          <p className="leading-relaxed">
            <strong className="text-slate-200">Stage {currentStage} Details:</strong> {stages[currentStage - 1].desc}
          </p>
          <span className="text-[11px] font-mono text-slate-400 shrink-0">
            {chaosDrift ? "Chaos Mode: Drift Sim Enabled" : "Nominal Production Flow"}
          </span>
        </div>
      </div>
    </div>
  );
}
