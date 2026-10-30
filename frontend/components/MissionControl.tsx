"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import {
  Activity,
  ArrowDownRight,
  ArrowRight,
  Check,
  ChevronRight,
  CircleDollarSign,
  Code2,
  Command,
  Cpu,
  Download,
  FlaskConical,
  Layers3,
  LoaderCircle,
  LockKeyhole,
  Radio,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  Terminal,
  Wallet,
  Zap,
} from "lucide-react";
import AttestationDrawer from "./AttestationDrawer";
import DeveloperDocs from "./DeveloperDocs";
import BenchmarkChart from "./BenchmarkChart";
import ConfidentialToggle from "./ConfidentialToggle";
import JobResultsViewer from "./JobResultsViewer";
import SimulationBanner from "./SimulationBanner";
import TelemetryGauges from "./TelemetryGauges";
import Link from "next/link";
import { INDUSTRY_BATCH_PRESETS } from "@/lib/batchPresets";
import { exportAuditCertificate } from "@/lib/AuditCertificate";
import { demoProviders, demoSnapshot, settleDemo } from "@/lib/simulation";
import {
  getProviderBadgeInfo,
  nodeState,
  usd,
  type Benchmark,
  type Job,
  type Provider,
  type Snapshot,
} from "@/lib/types";
import {
  api,
  createJob,
  getJob,
  getJobAttestations,
  getJobResults,
  getNodes,
  getTelemetry,
  getWebSocketTelemetryUrl,
  reconcilePayout,
  setDemoDrift,
  settleNow,
  type Attestation,
  type PromptResultItem,
} from "@/lib/api";
import { summarize } from "@/lib/benchmarks";

const Topology = dynamic(() => import("./Topology"), {
  ssr: false,
  loading: () => <div className="topology loading">Initializing network…</div>,
});

const isVercelRuntime =
  typeof window !== "undefined" &&
  (window.location.hostname.endsWith(".vercel.app") ||
    window.location.search.includes("mock=true"));

const SIMULATED =
  process.env.NEXT_PUBLIC_MOCK_FALLBACK === "true" ||
  process.env.VERCEL === "1" ||
  Boolean(process.env.NEXT_PUBLIC_VERCEL_ENV) ||
  isVercelRuntime;
type Log = { id: number; time: string; text: string; tone: string };

const NAV_ITEMS = [
  { id: "overview", label: "Overview / Mission Control", icon: Command, href: "#overview" },
  { id: "batch", label: "Batch Ingestion & Jobs", icon: Layers3, href: "#batch" },
  { id: "network", label: "Topology & Spot Swarm", icon: Cpu, href: "#network" },
  { id: "telemetry", label: "Live Telemetry", icon: Activity, href: "#telemetry" },
  { id: "settlement", label: "Settlement Ledger & PayPal", icon: Wallet, href: "#settlement" },
  { id: "verification", label: "Dev Mode & Chaos Injection", icon: FlaskConical, href: "#verification" },
  { id: "docs", label: "Developer API & SDK Hub", icon: Code2, href: "#docs" },
];

const QUICK_TEMPLATES = [
  {
    name: "Summarize Architecture",
    text: "Explain how verified inference protects a batch workload in one sentence.",
  },
  {
    name: "Math Canary Test",
    text: "Calculate step-by-step: 47 * 89 + 1337 and state all prime factors.",
  },
  {
    name: "JSON Extraction",
    text: "Extract key entities and JSON schema for an autonomous AI compute agreement.",
  },
];

export default function MissionControl() {
  const [confidential, setConfidential] = useState(true);
  const [providers, setProviders] = useState<Provider[]>(SIMULATED ? demoProviders : []);
  const [snapshot, setSnapshot] = useState<Snapshot>({ ts: 0, nodes: [], jobs: {} });
  const [connection, setConnection] = useState(SIMULATED ? "Simulation" : "Connecting");
  const [httpError, setHttpError] = useState("");
  const [benchmark, setBenchmark] = useState<Benchmark | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [attestations, setAttestations] = useState<Attestation[]>([]);
  const [logs, setLogs] = useState<Log[]>([]);
  const [slashed, setSlashed] = useState(false);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");
  const [prompt, setPrompt] = useState("");
  const [promptCount, setPromptCount] = useState(50);
  const [budget, setBudget] = useState("1.00");
  const [adminKey, setAdminKey] = useState("apex-demo-2026");
  const [modal, setModal] = useState(false);
  const [modalView, setModalView] = useState<"config" | "progress" | "results">("config");
  const [jobResults, setJobResults] = useState<any[] | null>(null);
  const [selectedPrompt, setSelectedPrompt] = useState<PromptResultItem | null>(null);
  const [isAttestationDrawerOpen, setIsAttestationDrawerOpen] = useState(false);
  const [selectedPresetId, setSelectedPresetId] = useState<string | null>(null);
  const [activeSection, setActiveSection] = useState("overview");
  const activeTab = activeSection;
  const isNavLockedRef = useRef(false);
  const navLockTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleNavClick = (sectionId: string) => {
    setActiveSection(sectionId);
    isNavLockedRef.current = true;
    if (navLockTimerRef.current) clearTimeout(navLockTimerRef.current);
    navLockTimerRef.current = setTimeout(() => {
      isNavLockedRef.current = false;
    }, 800);
  };
  const [lastBatch, setLastBatch] = useState<{ batch_id: string; status: string } | null>(null);
  const [retry, setRetry] = useState(0);
  const eventId = useRef(0);
  const loggedEvents = useRef<Set<string>>(new Set());
  const simulatedDone = useRef(0);
  const jobRef = useRef(job);
  jobRef.current = job;
  const settlementKey = useRef<string | null>(null);

  const addLog = useCallback((text: string, tone = "info") => {
    const id = ++eventId.current;
    setLogs((previous) =>
      [
        {
          id,
          time: new Date().toLocaleTimeString("en-GB", { hour12: false }),
          text,
          tone,
        },
        ...previous,
      ].slice(0, 40)
    );
  }, []);

  const initialized = useRef(false);
  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;
    if (!SIMULATED) {
      settlementKey.current = sessionStorage.getItem("apex-payout-retry");
      const saved = sessionStorage.getItem("apex-last-payout");
      if (saved) {
        try {
          setLastBatch(JSON.parse(saved));
        } catch {
          sessionStorage.removeItem("apex-last-payout");
        }
      }
    }
    addLog(
      SIMULATED
        ? "Simulation initialized. Confidential routing enabled."
        : "Mission Control initialized. Waiting for engine telemetry."
    );
  }, [addLog]);

  useEffect(() => {
    const sectionIds = [
      "overview",
      "batch",
      "network",
      "telemetry",
      "settlement",
      "verification",
      "docs",
    ];
    const observer = new IntersectionObserver(
      (entries) => {
        if (isNavLockedRef.current) return;
        const visible = entries.find((e) => e.isIntersecting);
        if (visible) setActiveSection(visible.target.id);
      },
      { rootMargin: "-20% 0px -60% 0px", threshold: 0.1 }
    );

    sectionIds.forEach((id) => {
      const el = document.getElementById(id);
      if (el) observer.observe(el);
    });

    return () => {
      observer.disconnect();
      if (navLockTimerRef.current) clearTimeout(navLockTimerRef.current);
    };
  }, []);

  useEffect(() => {
    if (!job || job.status !== "COMPLETED") return;
    let cancelled = false;
    const fetchResults = async () => {
      try {
        const results = SIMULATED
          ? Array.from({ length: job.total_prompts }, (_, i) => ({
              prompt_index: i,
              status: "SIMULATED",
              executing_node_id:
                job.sensitivity === "CONFIDENTIAL"
                  ? "nebius-nemotron-anchor"
                  : i % 2 === 0
                  ? "runpod-h100-spot-01"
                  : "community-spot-02",
              output_text:
                "Verified inference audits each batch before releasing node payment.",
              input_tokens: 32,
              output_tokens: 64,
            }))
          : await getJobResults(job.job_id);
        if (!cancelled) {
          const sorted = results.sort((a, b) => a.prompt_index - b.prompt_index);
          setJobResults(sorted);
          setModalView("results");
        }
      } catch (e) {
        console.warn("[MissionControl] Could not fetch reassembled results:", e);
      }
    };
    void fetchResults();
    return () => {
      cancelled = true;
    };
  }, [job?.job_id, job?.status]);

  useEffect(() => {
    let stopped = false;
    const load = async () => {
      try {
        const r = await fetch("/api/benchmarks", { cache: "no-store" });
        if (!r.ok) throw new Error("Could not read benchmark CSV");
        const ct = r.headers.get("content-type") || "";
        if (!ct.includes("application/json")) {
          throw new Error("Benchmark response was not JSON");
        }
        const b = await r.json();
        if (!stopped) setBenchmark(b);
      } catch (e) {
        if (!stopped) {
          console.warn("[MissionControl] Could not load benchmarks:", e);
        }
      }
    };
    void load();
    const timer = setInterval(load, 30000);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (SIMULATED) return;
    let stopped = false,
      loading = false;
    const load = async () => {
      if (loading) return;
      loading = true;
      try {
        const [registry, telemetry] = await Promise.allSettled([
          getNodes(),
          getTelemetry(),
        ]);
        if (stopped) return;
        if (registry.status === "rejected") {
          console.warn("[MissionControl] Engine unreachable, switching to zero-error simulation fallback:", registry.reason);
          setProviders(demoProviders);
          setSnapshot(demoSnapshot(0, confidential, slashed, 0, 0));
          setConnection("Simulation");
          setHttpError("");
          return;
        }
        const metrics = telemetry.status === "fulfilled" ? telemetry.value : [];
        setProviders(
          registry.value.map((p) => ({
            ...p,
            ...metrics.find((t) => t.node_id === p.node_id),
          }))
        );

        // Resilient Fallback: populate snapshot nodes from HTTP telemetry when WS is offline or snapshot empty
        setSnapshot((prev) => {
          if (connection !== "Live" || prev.nodes.length === 0) {
            return {
              ts: Date.now(),
              nodes: metrics.map((m) => {
                const existing = prev.nodes.find((n) => n.node_id === m.node_id);
                return {
                  node_id: m.node_id,
                  tokens_per_sec: m.tokens_per_sec,
                  p95_ttft_ms: m.p95_ttft_ms,
                  p50_ttft_ms: existing?.p50_ttft_ms ?? Math.round(m.p95_ttft_ms * 0.6),
                  error_rate: existing?.error_rate ?? 0,
                  active_requests: existing?.active_requests ?? 0,
                  status: existing?.status ?? "ACTIVE",
                };
              }),
              jobs: prev.jobs,
            };
          }
          return prev;
        });

        if (connection !== "Live" && connection !== "Connecting") {
          setConnection("Live (HTTP)");
        }
        setHttpError("");
      } catch (e) {
        if (!stopped) setHttpError((e as Error).message);
      } finally {
        loading = false;
      }
    };
    void load();
    const timer = setInterval(load, connection === "Live" ? 5000 : 2500);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [retry, connection]);

  useEffect(() => {
    if (SIMULATED) return;
    let disposed = false,
      socket: WebSocket | undefined,
      timer: ReturnType<typeof setTimeout>,
      delay = 1000,
      lastMessage = 0;

    function connect() {
      if (disposed) return;
      try {
        socket = new WebSocket(getWebSocketTelemetryUrl());
        socket.onopen = () => {
          if (disposed) return;
          lastMessage = Date.now();
          delay = 1000;
          setConnection("Live");
        };
        socket.onmessage = (event) => {
          if (disposed) return;
          try {
            const data = JSON.parse(event.data);
            if (
              !Array.isArray(data.nodes) ||
              typeof data.jobs !== "object" ||
              !Number.isFinite(data.ts)
            )
              throw new Error("Invalid snapshot");
            lastMessage = Date.now();
            setSnapshot(data);
            if (Array.isArray(data.events)) {
              for (const ev of data.events) {
                const key = `${ev.text}_${ev.time}`;
                if (!loggedEvents.current.has(key)) {
                  loggedEvents.current.add(key);
                  addLog(ev.text, ev.tone || "warning");
                }
              }
            }
          } catch {
            // Keep existing snapshot; do not throw uncaught error
          }
        };
        socket.onerror = () => {
          socket?.close();
        };
        socket.onclose = () => {
          if (disposed) return;
          setConnection("Reconnecting (HTTP Fallback)");
          timer = setTimeout(connect, delay);
          delay = Math.min(delay * 2, 10000);
        };
      } catch {
        setConnection("HTTP Polling (Fallback)");
        timer = setTimeout(connect, delay);
      }
    }
    connect();
    const watchdog = setInterval(() => {
      if (lastMessage && Date.now() - lastMessage > 5000) socket?.close();
    }, 2000);
    return () => {
      disposed = true;
      clearTimeout(timer);
      clearInterval(watchdog);
      try {
        socket?.close();
      } catch {}
    };
  }, [retry]);

  useEffect(() => {
    if (!SIMULATED) return;
    let tick = 0;
    const update = () => {
      tick++;
      const current = jobRef.current;
      if (current?.status === "RUNNING") {
        simulatedDone.current = Math.min(
          current.total_prompts,
          simulatedDone.current + Math.max(1, Math.ceil(current.total_prompts / 45))
        );
        if (simulatedDone.current === current.total_prompts) {
          setJob((j) =>
            j
              ? {
                  ...j,
                  status: "COMPLETED",
                  actual_settled_cost_micros: 923,
                  platform_fee_micros: 43,
                  total_makespan_ms: 45000,
                }
              : j
          );
          setProviders((previous) =>
            previous.map((p, i) => {
              const earned =
                current.sensitivity === "CONFIDENTIAL" ? i === 0 : i === 1;
              return earned
                ? { ...p, withdrawable_micros: p.withdrawable_micros + 923 }
                : p;
            })
          );
          addLog(
            "Demo batch completed. Outputs reassembled in prompt order; verified earnings credited.",
            "success"
          );
        }
      }
      setSnapshot(
        demoSnapshot(
          tick,
          current?.status === "RUNNING"
            ? current.sensitivity === "CONFIDENTIAL"
            : confidential,
          slashed,
          current?.total_prompts ?? 0,
          simulatedDone.current,
          current?.job_id
        )
      );
    };
    update();
    const timer = setInterval(update, 1000);
    return () => clearInterval(timer);
  }, [confidential, slashed, addLog]);

  useEffect(() => {
    if (SIMULATED || !job || !["QUEUED", "RUNNING"].includes(job.status)) return;
    let stopped = false,
      loading = false;
    const update = async () => {
      if (loading) return;
      loading = true;
      try {
        const [current, evidence] = await Promise.all([
          getJob(job.job_id),
          getJobAttestations(job.job_id),
        ]);
        if (!stopped) {
          setJob(current);
          setAttestations(evidence);
          if (Array.isArray(evidence)) {
            for (const att of evidence) {
              if (att.status === "VERIFIED_FAIL_REROUTED") {
                const key = `quarantine_${att.node_id}_${att.shred_id}`;
                if (!loggedEvents.current.has(key)) {
                  loggedEvents.current.add(key);
                  addLog(
                    `[QUARANTINE] Node ${att.node_id} failed canary audit. Rerouting prompts to Nebius Anchor.`,
                    "danger"
                  );
                }
              }
            }
          }
          if (!["RUNNING", "QUEUED"].includes(current.status))
            addLog(
              `Batch ${current.status.toLowerCase()}. Cost ${usd(
                current.actual_settled_cost_micros
              )}.`,
              current.status === "COMPLETED" ? "success" : "warning"
            );
        }
      } catch (e) {
        if (!stopped) setNotice((e as Error).message);
      } finally {
        loading = false;
      }
    };
    void update();
    const timer = setInterval(update, 1500);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [job?.job_id, job?.status, addLog]);

  useEffect(() => {
    if (
      SIMULATED ||
      !adminKey ||
      !lastBatch ||
      lastBatch.status !== "SUBMITTED_PENDING"
    )
      return;
    let stopped = false,
      loading = false;
    const reconcile = async () => {
      if (loading) return;
      loading = true;
      try {
        const receipt = await reconcilePayout(lastBatch.batch_id, adminKey);
        if (!stopped && receipt.status !== lastBatch.status) {
          setLastBatch(receipt);
          sessionStorage.setItem("apex-last-payout", JSON.stringify(receipt));
          addLog(
            `PayPal Sandbox payout ${receipt.status.toLowerCase()}.`,
            receipt.status === "COMPLETED" ? "success" : "warning"
          );
          setRetry((n) => n + 1);
        }
      } catch (e) {
        if (!stopped) setNotice((e as Error).message);
      } finally {
        loading = false;
      }
    };
    void reconcile();
    const timer = setInterval(reconcile, 5000);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [adminKey, lastBatch?.batch_id, lastBatch?.status, addLog]);

  const displaySnapshot: Snapshot = {
    ...snapshot,
    nodes: providers.map((provider) => {
      const live = snapshot.nodes.find((node) => node.node_id === provider.node_id) ?? {
        node_id: provider.node_id,
        status: "ACTIVE",
        active_requests: 0,
        p50_ttft_ms: 0,
        p95_ttft_ms: 0,
        error_rate: 0,
      };
      return attestations.some(
        (a) => a.node_id === provider.node_id && a.status === "VERIFIED_FAIL_REROUTED"
      )
        ? { ...live, status: "SLASHED" }
        : live;
    }),
  };

  const totalWithdrawable = providers.reduce(
    (n, p) => n + p.withdrawable_micros,
    0
  );
  const pending = providers.reduce((n, p) => n + p.payout_pending_micros, 0);
  const held = providers.reduce((n, p) => n + p.pending_probation_micros, 0);
  const throughput = (snapshot.nodes.length > 0 ? snapshot.nodes : providers).reduce(
    (sum, p) =>
      sum +
      (p.tokens_per_sec ??
        providers.find((n) => n.node_id === p.node_id)?.tokens_per_sec ??
        0),
    0
  );
  const progress = job ? snapshot.jobs[job.job_id] : undefined;
  const done = job?.status === "COMPLETED" ? job.total_prompts : progress?.done ?? 0;
  const running = !!job && ["RUNNING", "QUEUED"].includes(job.status);
  const graphConfidential = running ? job.sensitivity === "CONFIDENTIAL" : confidential;
  const baseline = summarize(benchmark?.rows ?? [], "DEFAULT_PROVIDER_BASELINE");
  const apex = summarize(benchmark?.rows ?? [], "APEXMARKET_VERIFIED_ROUTER");
  const savings = baseline && apex ? (1 - apex.cost / baseline.cost) * 100 : null;

  function togglePrivacy() {
    setConfidential((value) => !value);
    addLog(
      confidential
        ? "Next batch classified SYNTHETIC. Verified spot routing enabled."
        : "Next batch classified CONFIDENTIAL. Trusted anchor only.",
      "success"
    );
  }

  async function launch() {
    const trimmed = prompt.trim();
    if (!trimmed) {
      setNotice("Please enter at least one prompt or select a quick template above.");
      return;
    }
    const lines = trimmed.split("\n").filter((p) => p.trim());
    const micros = Math.round(Number(budget) * 1_000_000);
    if (
      !/^\d+(?:\.\d{1,6})?$/.test(budget) ||
      !lines.length ||
      lines.some((p) => p.length > 32000) ||
      !Number.isInteger(promptCount) ||
      promptCount < 1 ||
      promptCount > 5000 ||
      !Number.isSafeInteger(micros) ||
      micros < 1 ||
      micros > 100000000
    ) {
      setNotice(
        "Use 1–5,000 prompts, up to 32,000 characters each, and a budget from $0.000001 to $100."
      );
      return;
    }
    setBusy("launch");
    setNotice("");
    setAttestations([]);
    setJobResults(null);
    try {
      const sensitivity = confidential ? "CONFIDENTIAL" : "SYNTHETIC";
      if (SIMULATED) {
        simulatedDone.current = 0;
        setJob({
          job_id: crypto.randomUUID(),
          status: "RUNNING",
          sensitivity,
          total_prompts: promptCount,
          actual_settled_cost_micros: 0,
          platform_fee_micros: 0,
          reserved_escrow_micros: micros,
        });
      } else {
        setJob(
          await createJob({
            sensitivity,
            prompts: Array.from({ length: promptCount }, (_, i) => ({
              prompt_index: i,
              content: lines[i % lines.length],
            })),
            max_tokens_per_prompt: 128,
            max_cost_ceiling_micros: micros,
            makespan_sla_seconds: 120,
            target_model: "meta-llama/Llama-3.1-8B-Instruct",
          })
        );
      }
      addLog(
        `${SIMULATED ? "Demo" : "Live"} batch submitted · ${promptCount} prompts · ${sensitivity}.`,
        "success"
      );
      setModalView("progress");
    } catch (e) {
      setNotice((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  async function injectDrift() {
    setBusy("drift");
    setNotice("");
    try {
      if (!SIMULATED) await setDemoDrift(!slashed, adminKey);
      setSlashed((v) => !v);
      addLog(
        slashed
          ? "Mock provider restored to honest outputs."
          : SIMULATED
          ? "Demo drift detected. Corrupted shreds rejected; prompts rerouted to anchor."
          : "Mock provider set to degraded output. Subsequent batch attestations show verification results.",
        slashed ? "success" : "warning"
      );
    } catch (e) {
      setNotice((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  async function settle() {
    setBusy("settle");
    setNotice("");
    try {
      if (SIMULATED) {
        const next = settleDemo(providers);
        setProviders(next);
        const amount =
          next.reduce((n, p) => n + p.payout_pending_micros, 0) - pending;
        addLog(
          `Simulated payout submitted · ${usd(amount, 2)} · sub-cent remainder retained.`,
          "success"
        );
        setNotice(
          `Simulated sandbox batch submitted: ${usd(amount, 2)}. No money was moved.`
        );
      } else {
        settlementKey.current ??= crypto.randomUUID();
        sessionStorage.setItem("apex-payout-retry", settlementKey.current);
        const receipt = await settleNow(adminKey, settlementKey.current);
        addLog(
          `PayPal Sandbox · ${receipt.status} · ${usd(
            receipt.total_amount_micros,
            2
          )} · ${receipt.batch_id}`,
          "success"
        );
        setNotice(
          `Sandbox payout ${receipt.status.toLowerCase()}: ${usd(
            receipt.total_amount_micros,
            2
          )}. Receipt ${receipt.batch_id}`
        );
        settlementKey.current = null;
        sessionStorage.removeItem("apex-payout-retry");
        setLastBatch(receipt);
        sessionStorage.setItem("apex-last-payout", JSON.stringify(receipt));
        setRetry((r) => r + 1);
      }
    } catch (e) {
      setNotice((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  async function downloadResults() {
    if (!job) return;
    setBusy("results");
    try {
      const results = SIMULATED
        ? Array.from({ length: job.total_prompts }, (_, i) => ({
            prompt_index: i,
            status: "SIMULATED",
            executing_node_id:
              job.sensitivity === "CONFIDENTIAL"
                ? "nebius-nemotron-anchor"
                : i % 2 === 0
                ? "runpod-h100-spot-01"
                : "community-spot-02",
            output_text:
              "Verified inference audits each batch before releasing node payment.",
            input_tokens: 32,
            output_tokens: 64,
          }))
        : await getJobResults(job.job_id);
      const url = URL.createObjectURL(
        new Blob(
          [JSON.stringify(results.sort((a, b) => a.prompt_index - b.prompt_index), null, 2)],
          { type: "application/json" }
        )
      );
      const link = document.createElement("a");
      link.href = url;
      link.download = `${SIMULATED ? "simulated-" : ""}${job.job_id}.json`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setNotice((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  function handleExportAudit() {
    if (!job) return;
    exportAuditCertificate(
      job,
      attestations,
      (jobResults as PromptResultItem[]) || [],
      slashed ? ["runpod-h100-spot-01"] : []
    );
    addLog(
      `Cryptographic attestation bundle exported for batch ${job.job_id.slice(0, 8)}.`,
      "success"
    );
  }

  const failedEvidence = attestations.some(
    (a) => a.status === "VERIFIED_FAIL_REROUTED"
  );
  const rejected = SIMULATED ? slashed : failedEvidence;
  const tiers = [
    {
      name: "Authoritative token billing",
      detail: "Local tokenizer · provider-independent",
      value:
        SIMULATED && job
          ? "Active"
          : attestations.length
          ? "Recorded"
          : "Ready",
    },
    {
      name: "Rotated canary probes",
      detail: "4% dynamic challenge injection",
      value:
        SIMULATED && slashed
          ? "Rejected"
          : attestations.some((a) => a.canary_pass_rate !== null)
          ? "Recorded"
          : "Ready",
    },
    {
      name: "Secret anchor sampling",
      detail: "5% reference comparison",
      value: SIMULATED && job ? "Demo" : "Policy",
    },
    {
      name: "Anchor logprob scoring",
      detail: "Teacher-forcing negative log-likelihood",
      value:
        SIMULATED && slashed
          ? "Demo spike"
          : attestations.some((a) => a.anchor_nll_score !== null)
          ? "Recorded"
          : "Policy",
    },
    {
      name: "Nemotron semantic judge",
      detail: "Borderline output arbitration",
      value:
        SIMULATED && slashed
          ? "Demo reject"
          : attestations.some((a) => a.nemotron_judge_score !== null)
          ? "Recorded"
          : "Policy",
    },
  ];

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a href="#overview" className="brand-mark" aria-label="ApexMarket home">
          <Zap size={24} fill="currentColor" />
        </a>
        <nav className="flex flex-col items-center gap-3 w-full" aria-label="Main Navigation">
          {NAV_ITEMS.map((item) => {
            const isSelected = activeSection === item.id;
            return (
              <div key={item.id} className="relative group flex items-center justify-center w-full px-2">
                <a
                  href={item.href}
                  onClick={() => handleNavClick(item.id)}
                  className={`nav-icon transition-all duration-150 flex items-center justify-center ${
                    isSelected
                      ? "text-emerald-400 bg-emerald-500/10 border-l-2 border-emerald-400 shadow-sm shadow-emerald-500/10"
                      : "text-slate-400 hover:text-slate-100 hover:bg-slate-800/60"
                  }`}
                  aria-label={item.label}
                  aria-current={isSelected ? "page" : undefined}
                >
                  <item.icon size={20} />
                </a>
                <div
                  role="tooltip"
                  className="pointer-events-none absolute left-full ml-3 hidden md:flex items-center px-2.5 py-1 rounded-md bg-slate-900 border border-slate-700/80 text-xs font-medium text-slate-100 whitespace-nowrap shadow-xl opacity-0 translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-150 z-50"
                >
                  {item.label}
                </div>
              </div>
            );
          })}
        </nav>
        <div className="sidebar-bottom">
          <span className="environment-dot" />
          <span className="text-xs text-slate-400 font-semibold tracking-wider">DEV</span>
        </div>
      </aside>
      <div className="workspace" id="overview">
        {SIMULATED && <SimulationBanner />}
        <header className="topbar">
          <a href="#overview" className="wordmark">
            apex<span>market</span>
            <span className="version">/ mission control</span>
          </a>
          <div className="topbar-right">
            <Link
              href="/verify"
              className="px-2.5 py-1 rounded text-xs font-semibold bg-[#70e4bf1a] text-[#70e4bf] border border-[#70e4bf33] hover:bg-[#70e4bf2a] transition-colors flex items-center gap-1.5"
            >
              <ShieldCheck size={13} /> Verify Audit Bundle
            </Link>
            <Link
              href="/architecture"
              className="px-2.5 py-1 rounded text-xs font-semibold bg-[#1a2638] text-slate-300 border border-[#2a3c54] hover:text-white transition-colors"
            >
              Architecture
            </Link>
            <span
              className={`connection ${
                connection === "Live" || SIMULATED ? "healthy" : ""
              }`}
            >
              <span className="dot" />
              {connection}
            </span>
            <span className="environment">SANDBOX</span>
            <span className="avatar">AM</span>
          </div>
        </header>
        <main>
          <div className="page-heading">
            <div>
              <div className="flex flex-wrap items-center gap-2.5 mb-2">
                <div className="eyebrow !mb-0">
                  INFERENCE OPERATIONS <ChevronRight size={12} /> OVERVIEW
                </div>
                <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[10px] font-bold tracking-wider uppercase bg-[#70e4bf14] border border-[#70e4bf55] text-[#70e4bf] shadow-[0_0_15px_rgba(112,228,191,0.2)]">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#70e4bf] shadow-[0_0_6px_#70e4bf] animate-ping" />
                  POWERED BY NEBIUS TOKEN FACTORY · NVIDIA NEMOTRON-3-NANO ANCHOR
                </span>
              </div>
              <h1>
                Mission Control<span>.</span>
              </h1>
              <p>Route intelligently. Verify every shred. Settle with confidence.</p>
            </div>
            <button
              className="primary"
              onClick={() => {
                if (running) setModalView("progress");
                else if (jobResults && job?.status === "COMPLETED") setModalView("results");
                else setModalView("config");
                setModal(true);
              }}
              disabled={!!busy}
            >
              <Zap size={15} /> Launch batch <ArrowRight size={15} />
            </button>
          </div>
          {(notice || httpError) && (
            <div className="notice" role="status">
              <span>{notice || httpError}</span>
              <button
                aria-label="Dismiss message"
                onClick={() => {
                  setNotice("");
                  setHttpError("");
                }}
              >
                ×
              </button>
            </div>
          )}
          {!SIMULATED && !["Live", "Connecting"].includes(connection) && (
            <div className="connection-warning">
              Telemetry reconnecting. Last snapshot is retained.{" "}
              <button onClick={() => setRetry((r) => r + 1)}>Reconnect</button>
            </div>
          )}
          <div className="metrics-grid">
            <Metric
              label="VERIFIED COST SAVINGS"
              value={savings === null ? "—" : `${savings.toFixed(2)}%`}
              suffix="vs. single provider"
              icon={<ArrowDownRight size={18} />}
              detail="Repository benchmark · includes audit compute"
              accent
            />
            <Metric
              label="NETWORK THROUGHPUT"
              value={Math.round(throughput).toLocaleString()}
              suffix="tok/s"
              icon={<Activity size={18} />}
              detail={
                SIMULATED
                  ? "Simulated · updates every second"
                  : "Rolling provider telemetry"
              }
            />
            <Metric
              label="ACTIVE PROVIDERS"
              value={`${
                providers.filter(
                  (p) =>
                    p.is_active &&
                    nodeState(
                      displaySnapshot.nodes.find((n) => n.node_id === p.node_id),
                      p.is_active
                    ) !== "slashed"
                ).length
              }`.padStart(2, "0")}
              suffix={`/ ${providers.length.toString().padStart(2, "0")} registered`}
              icon={<Cpu size={18} />}
              detail={
                graphConfidential
                  ? "Trusted anchor routing enforced"
                  : "Verified multi-provider routing"
              }
            />
            <Metric
              label="WITHDRAWABLE BALANCE"
              value={usd(totalWithdrawable, 2)}
              suffix="USD"
              icon={<CircleDollarSign size={18} />}
              detail={`${totalWithdrawable.toLocaleString()} integer micro-dollars`}
            />
          </div>

          {/* Real-Time Telemetry & Hardware Gauges Section */}
          <section className="panel telemetry-panel mb-6" id="telemetry">
            <div className="panel-heading">
              <div>
                <div className="eyebrow">
                  <Activity size={14} /> REAL-TIME TELEMETRY &amp; HARDWARE GAUGES
                </div>
                <h2>Live infrastructure latency, token velocity, and audit overhead</h2>
              </div>
              <span className="pill">
                <span className="dot optimal" />{" "}
                {connection === "Live" ? "10 HZ WEBSOCKET" : "STREAMING METRICS"}
              </span>
            </div>
            <div className="mt-4">
              <TelemetryGauges
                snapshot={displaySnapshot}
                providers={providers}
                liveThroughput={throughput}
              />
            </div>
          </section>

          <div className="main-grid">
            <section className="panel network-panel" id="network">
              <div className="panel-heading">
                <div>
                  <div className="eyebrow">
                    <Radio size={14} /> NETWORK TOPOLOGY
                  </div>
                  <h2>One router. Verified compute.</h2>
                </div>
                <span className="pill">
                  <span className="dot optimal" />{" "}
                  {SIMULATED ? "DEMO NETWORK" : "LIVE NETWORK"}
                </span>
              </div>
              <ConfidentialToggle
                confidential={confidential}
                onToggle={togglePrivacy}
                disabled={running}
              />
              <Topology
                providers={providers}
                snapshot={displaySnapshot}
                confidential={graphConfidential}
              />
              <div className="graph-footer">
                <div>
                  <span>
                    <i className="dot optimal" /> Optimal
                  </span>
                  <span>
                    <i className="dot slow" /> Slow
                  </span>
                  <span>
                    <i className="dot slashed" /> Slashed
                  </span>
                </div>
                <span>Edge width ∝ throughput</span>
              </div>
            </section>
            <section className="panel verification-panel" id="verification">
              <div className="panel-heading">
                <div>
                  <div className="eyebrow">
                    <ShieldCheck size={14} /> PROOF BEFORE PAYMENT
                  </div>
                  <h2>Verification pipeline</h2>
                </div>
                <span className="pill muted">5 TIERS</span>
              </div>
              <div className="tier-list">
                {tiers.map((tier, i) => {
                  const isFailed =
                    tier.value.includes("reject") ||
                    tier.value === "Rejected" ||
                    tier.value.includes("spike");
                  const isActive =
                    tier.value === "Active" ||
                    tier.value === "Ready" ||
                    tier.value === "Recorded";
                  return (
                    <div
                      className={`tier py-3 flex items-center gap-3 border-b border-slate-800/80 ${
                        isFailed ? "failed" : ""
                      }`}
                      key={tier.name}
                    >
                      <span className="tier-index text-sm font-mono text-slate-300 font-medium w-6">
                        0{i + 1}
                      </span>
                      <div className="flex-1">
                        <strong className="text-sm font-medium text-slate-100 block">
                          {tier.name}
                        </strong>
                        <span className="text-xs text-slate-400 leading-relaxed block mt-0.5">
                          {tier.detail}
                        </span>
                      </div>
                      <span
                        className={`px-2.5 py-1 rounded text-xs font-medium border ${
                          isFailed
                            ? "bg-red-500/15 text-red-300 border-red-500/30"
                            : isActive
                            ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
                            : "bg-slate-800/80 text-slate-300 border border-slate-700/70"
                        }`}
                      >
                        {tier.value}
                      </span>
                    </div>
                  );
                })}
              </div>
              <div className={`verification-note ${rejected ? "danger" : ""}`}>
                <ShieldCheck size={19} />
                <div>
                  <strong className="text-sm font-medium text-slate-100 block">
                    {rejected ? "Corrupted shred rejected" : "Every payout starts with proof"}
                  </strong>
                  <p className="text-xs text-slate-300 mt-1 leading-relaxed">
                    {rejected
                      ? "Failed output earns no payout. Unverified prompts route to the trusted anchor."
                      : "Only verified work earns a ledger credit. Attestations protect the settlement boundary."}
                  </p>
                </div>
              </div>
              <div className="relative group w-full">
                <button
                  className={`chaos-button ${slashed ? "restore" : ""}`}
                  onClick={injectDrift}
                  disabled={!!busy || confidential || (!SIMULATED && !adminKey)}
                  title={confidential ? "Disabled: Confidential workloads never touch third-party spot nodes" : undefined}
                >
                  {busy === "drift" ? (
                    <LoaderCircle size={15} className="spin" />
                  ) : slashed ? (
                    <RotateCcw size={15} />
                  ) : (
                    <FlaskConical size={15} />
                  )}
                  {slashed ? "Restore honest provider" : "Inject INT4 quantization drift"}
                  <span>{SIMULATED ? "DEMO" : "MOCK"}</span>
                </button>
                {confidential && (
                  <div
                    role="tooltip"
                    className="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden group-hover:flex items-center px-3 py-1.5 rounded-md bg-slate-900 border border-slate-700 text-xs font-medium text-amber-300 whitespace-nowrap shadow-xl z-50"
                  >
                    Disabled: Confidential workloads never touch third-party spot nodes
                  </div>
                )}
              </div>
              <p className="fine-print text-xs text-slate-400">
                {confidential
                  ? "Disabled: Confidential workloads never touch third-party spot nodes."
                  : "Chaos changes only the configured local mock provider."}
              </p>
            </section>
          </div>
          <JobResultsViewer
            job={job}
            done={done}
            running={running}
            busy={busy}
            results={jobResults}
            onOpenModal={() => setModal(true)}
            onDownload={downloadResults}
            onExportAudit={handleExportAudit}
            onInspectProof={(p) => {
              setSelectedPrompt(p || jobResults?.[0] || null);
              setIsAttestationDrawerOpen(true);
            }}
          />
          <div className="bottom-grid">
            <BenchmarkChart benchmark={benchmark} />
            <section className="panel settlement-panel" id="settlement">
              <div className="panel-heading">
                <div>
                  <div className="eyebrow">
                    <Wallet size={14} /> SETTLEMENT ENGINE
                  </div>
                  <h2>Small units. Exact accounting.</h2>
                </div>
                <span className="paypal-mark">
                  Pay<span>Pal</span>
                </span>
              </div>
              <div className="balance-display">
                <span>Available for settlement</span>
                <strong>
                  {usd(totalWithdrawable, 6)}
                  <small>USD</small>
                </strong>
                <p>
                  {totalWithdrawable.toLocaleString()} micros <span>·</span> integer precision
                </p>
              </div>
              <div className="ledger-breakdown">
                <div>
                  <span>Probation escrow</span>
                  <b>{usd(held)}</b>
                </div>
                <div>
                  <span>Payout pending</span>
                  <b>{usd(pending)}</b>
                </div>
                <div>
                  <span>Sub-cent carry after payout</span>
                  <b>
                    {usd(
                      providers.reduce(
                        (n, p) => n + (p.withdrawable_micros % 10000),
                        0
                      )
                    )}
                  </b>
                </div>
              </div>
              {!SIMULATED && (
                <label className="admin-label">
                  Sandbox admin key
                  <input
                    type="password"
                    autoComplete="off"
                    value={adminKey}
                    onChange={(e) => setAdminKey(e.target.value)}
                    placeholder="Enter session key"
                  />
                </label>
              )}
              <button
                className="settle-button"
                onClick={settle}
                disabled={
                  !!busy ||
                  providers.every((p) => p.withdrawable_micros < 10000) ||
                  (!SIMULATED && !adminKey)
                }
              >
                {busy === "settle" ? (
                  <LoaderCircle size={16} className="spin" />
                ) : (
                  <Wallet size={16} />
                )}{" "}
                Settle now (Sandbox) <ArrowRight size={16} />
              </button>
              {lastBatch && (
                <p className="payout-receipt">
                  Batch {lastBatch.batch_id.slice(0, 8)} ·{" "}
                  {lastBatch.status.replaceAll("_", " ")}
                </p>
              )}
              <p className="fine-print">
                <LockKeyhole size={11} />{" "}
                {SIMULATED
                  ? "Simulated payouts · no external money movement"
                  : "Sandbox only · idempotent payouts · $0.01 minimum"}
              </p>
            </section>
          </div>
          <section className="panel activity-panel">
            <div className="activity-heading">
              <div className="eyebrow">
                <Terminal size={14} /> EVENT STREAM
              </div>
              <span>{SIMULATED ? "SIMULATED" : "SESSION EVENTS"}</span>
            </div>
            <div className="event-list" aria-live="polite" aria-relevant="additions">
              {logs.slice(0, 5).map((log) => (
                <div className={`event ${log.tone}`} key={log.id}>
                  <time>{log.time}</time>
                  <span className="dot" />
                  <p>{log.text}</p>
                </div>
              ))}
            </div>
          </section>
          <div className="mt-6 mb-2">
            <DeveloperDocs />
          </div>
          <footer>
            <span>
              <Zap size={12} /> APEXMARKET <b>/</b> Verified inference infrastructure
            </span>
            <div className="flex items-center gap-4 text-xs text-slate-400">
              <Link href="/verify" className="hover:text-slate-200">
                Verify Audit Bundle
              </Link>
              <span>·</span>
              <Link href="/architecture" className="hover:text-slate-200">
                System Architecture
              </Link>
              <span>·</span>
              <span>
                CONFIDENTIAL by default <span className="dot optimal" />
              </span>
            </div>
          </footer>
        </main>
      </div>
      {modal && (
        <div
          className="modal-backdrop"
          onClick={(e) => {
            if (e.target === e.currentTarget && !busy) setModal(false);
          }}
        >
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="batch-title"
            className="batch-modal"
            onKeyDown={(e) => {
              if (e.key === "Escape") setModal(false);
              if (e.key === "Tab") {
                const focusable = e.currentTarget.querySelectorAll<HTMLElement>(
                  "button:not(:disabled), input, textarea, select"
                );
                const first = focusable[0],
                  last = focusable[focusable.length - 1];
                if (e.shiftKey && document.activeElement === first) {
                  e.preventDefault();
                  last.focus();
                } else if (!e.shiftKey && document.activeElement === last) {
                  e.preventDefault();
                  first.focus();
                }
              }
            }}
          >
            <div className="panel-heading">
              <div>
                <div className="eyebrow">
                  {modalView === "results"
                    ? "REASSEMBLED OUTPUTS"
                    : modalView === "progress"
                    ? "ACTIVE INFERENCE STREAM"
                    : "NEW WORKLOAD"}
                </div>
                <h2 id="batch-title">
                  {modalView === "results"
                    ? "Batch Prompt Results"
                    : modalView === "progress"
                    ? "Batch in Execution"
                    : "Launch a verified batch"}
                </h2>
              </div>
              <button
                className="close-button"
                aria-label="Close batch configuration"
                onClick={() => setModal(false)}
              >
                ×
              </button>
            </div>

            {modalView === "progress" && job && (
              <div className="modal-progress-view space-y-4 my-2">
                <div className="flex items-center justify-between p-3 rounded-lg bg-slate-900/80 border border-slate-800">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono text-slate-400">Job ID:</span>
                    <strong className="text-xs font-mono text-slate-100">{job.job_id.slice(0, 13)}…</strong>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 rounded text-xs font-medium border border-emerald-500/30 bg-emerald-500/10 text-emerald-300">
                      {job.sensitivity}
                    </span>
                    <span className="px-2 py-0.5 rounded text-xs font-medium border border-blue-500/30 bg-blue-500/10 text-blue-300 animate-pulse">
                      {job.status}
                    </span>
                  </div>
                </div>

                <div className="batch-progress my-4">
                  <div className="flex justify-between text-xs text-slate-300 mb-1.5">
                    <span>{done} / {job.total_prompts} prompts complete</span>
                    <b className="font-semibold text-emerald-400">
                      {job.total_prompts > 0 ? Math.round((done / job.total_prompts) * 100) : 0}%
                    </b>
                  </div>
                  <progress max={job.total_prompts} value={done} className="w-full h-2 rounded bg-slate-800" />
                </div>

                <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80 text-xs text-slate-400 space-y-1.5">
                  <div className="flex items-center gap-2 text-emerald-400 font-medium">
                    <LoaderCircle size={14} className="spin" />
                    <span>Streaming shreds & validating canaries across node swarm…</span>
                  </div>
                  <p className="text-slate-400 text-xs leading-relaxed">
                    Outputs are cryptographically attested and reassembled in original prompt index order. Results will appear automatically on completion.
                  </p>
                </div>

                {job.status === "COMPLETED" && (
                  <button
                    className="primary w-full mt-4 text-xs font-semibold py-2.5"
                    onClick={() => setModalView("results")}
                  >
                    View Reassembled Results <ArrowRight size={15} />
                  </button>
                )}
              </div>
            )}

            {modalView === "results" && jobResults && (
              <div className="modal-results-view space-y-4 my-2">
                <div className="flex items-center justify-between p-3 rounded-lg bg-slate-900/80 border border-slate-800">
                  <div>
                    <div className="text-xs text-slate-400">Total Processed</div>
                    <strong className="text-sm text-slate-100 font-mono">{jobResults.length} prompts</strong>
                  </div>
                  <div>
                    <div className="text-xs text-slate-400">Settled Cost</div>
                    <strong className="text-sm text-emerald-400 font-mono">{usd(job?.actual_settled_cost_micros ?? 0)}</strong>
                  </div>
                  <div>
                    <div className="text-xs text-slate-400">Target Model</div>
                    <strong className="text-xs text-slate-300 font-mono">Llama-3.1-8B</strong>
                  </div>
                </div>

                <div className="max-h-72 overflow-y-auto space-y-2 pr-1 border border-slate-800/80 rounded-lg p-2 bg-slate-950/50">
                  {jobResults.map((item) => {
                    const badgeInfo = getProviderBadgeInfo(item.executing_node_id, item.prompt_index);
                    const inTokens = item.input_tokens ?? 32;
                    const outTokens = item.output_tokens ?? 64;
                    const totalTokens = inTokens + outTokens;
                    const shredMicroCost = inTokens * badgeInfo.inRateMicros + outTokens * badgeInfo.outRateMicros;

                    return (
                      <div key={item.prompt_index} className="p-2.5 rounded-lg bg-slate-900/90 border border-slate-800/90 text-xs space-y-1.5">
                        <div className="flex items-center justify-between gap-2 flex-wrap">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-mono font-semibold text-emerald-400">Prompt #{item.prompt_index + 1}</span>
                            <span className={`px-2 py-0.5 rounded text-[10px] font-semibold tracking-wide ${badgeInfo.className}`}>
                              {badgeInfo.label}
                            </span>
                            <span className="text-slate-300 font-mono text-[11px] bg-slate-800/90 px-2 py-0.5 rounded border border-slate-700/60">
                              <b className="text-emerald-400 font-medium">{totalTokens}</b> tokens
                            </span>
                            <span className="text-slate-300 font-mono text-[11px] bg-slate-800/90 px-2 py-0.5 rounded border border-slate-700/60">
                              cost: <b className="text-slate-100 font-medium">{usd(Math.round(shredMicroCost), 6)}</b>
                            </span>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-emerald-500/10 text-emerald-300 border border-emerald-500/30">
                              {item.status}
                            </span>
                            <button
                              type="button"
                              className="px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-500/15 text-amber-300 border border-amber-500/40 hover:bg-amber-500/25 transition-colors"
                              onClick={() => {
                                setSelectedPrompt(item);
                                setIsAttestationDrawerOpen(true);
                              }}
                            >
                              Inspect Proof
                            </button>
                          </div>
                        </div>
                        <p className="text-slate-200 text-xs leading-relaxed font-sans">{item.output_text}</p>
                      </div>
                    );
                  })}
                </div>

                <div className="flex items-center gap-3 pt-2">
                  <button
                    className="secondary flex-1 justify-center py-2.5 text-xs font-medium"
                    onClick={downloadResults}
                    disabled={busy === "results"}
                  >
                    {busy === "results" ? <LoaderCircle size={14} className="spin" /> : <Download size={14} />} Download JSON
                  </button>
                  <button
                    className="secondary flex-1 justify-center py-2.5 text-xs font-medium border-[#70e4bf55] text-[#70e4bf] hover:bg-[#70e4bf15]"
                    onClick={handleExportAudit}
                  >
                    <ShieldCheck size={14} /> Export Attestation Bundle
                  </button>
                  <button
                    className="primary flex-1 justify-center py-2.5 text-xs font-medium"
                    onClick={() => {
                      setModalView("config");
                      setPrompt("");
                    }}
                  >
                    Configure New Batch
                  </button>
                </div>
              </div>
            )}

            {modalView === "config" && (
              <>
                {/* Industry Batch Presets */}
                <div className="industry-presets my-2.5">
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-xs font-semibold text-slate-200 flex items-center gap-1.5">
                      <Sparkles size={13} className="text-[#70e4bf]" /> Quick Industry Batches (1-Click)
                    </span>
                    <span className="text-[10px] text-slate-400 font-mono">Enterprise Presets</span>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                    {INDUSTRY_BATCH_PRESETS.map((preset) => {
                      const isSelected = selectedPresetId === preset.id;
                      return (
                        <button
                          key={preset.id}
                          type="button"
                          className={`p-2.5 rounded-lg text-left border transition-all ${
                            isSelected
                              ? "bg-[#70e4bf15] border-[#70e4bf] text-slate-100 shadow-sm shadow-[#70e4bf10]"
                              : "bg-slate-900/80 border-slate-800 hover:border-slate-700 text-slate-300"
                          }`}
                          onClick={() => {
                            setSelectedPresetId(preset.id);
                            setPrompt(preset.prompts.join("\n"));
                            setPromptCount(preset.promptCount);
                            setBudget(preset.budget);
                            setConfidential(preset.sensitivity === "CONFIDENTIAL");
                          }}
                        >
                          <div className="flex items-center justify-between text-xs font-medium mb-1">
                            <span className="text-slate-100 truncate font-semibold">{preset.title}</span>
                            {isSelected && <Check size={13} className="text-[#70e4bf] shrink-0" />}
                          </div>
                          <div className="text-[10px] font-mono text-[#70e4bf] font-medium">{preset.tag}</div>
                          <div className="text-[11px] text-slate-400 mt-1 line-clamp-2 leading-tight">
                            {preset.description}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="quick-templates my-2">
                  <div className="text-xs text-slate-300 font-medium mb-1.5">Quick Templates:</div>
                  <div className="flex flex-wrap gap-1.5">
                    {QUICK_TEMPLATES.map((tmpl) => (
                      <button
                        key={tmpl.name}
                        type="button"
                        className="text-xs px-2.5 py-1 rounded bg-slate-800/90 hover:bg-slate-700 text-slate-200 border border-slate-700/80 hover:border-emerald-500/50 transition-colors"
                        onClick={() => setPrompt(tmpl.text)}
                      >
                        {tmpl.name}
                      </button>
                    ))}
                  </div>
                </div>

                <label className="block mt-3">
                  <span className="text-xs font-medium text-slate-200">Prompt templates</span>{" "}
                  <small className="text-xs text-slate-400 block mt-0.5">One per line, repeated to fill the batch</small>
                  <textarea
                    autoFocus
                    rows={4}
                    placeholder="Explain how verified inference protects a batch workload in one sentence, or enter custom prompts..."
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    className="w-full mt-2 p-2.5 bg-slate-950 border border-slate-700 rounded text-xs text-slate-100 placeholder:text-slate-400 focus:outline-none focus:border-emerald-500"
                  />
                </label>

                <div className="form-row my-3">
                  <label className="text-xs text-slate-200">
                    Prompt count
                    <input
                      type="number"
                      min="1"
                      max="5000"
                      value={promptCount}
                      onChange={(e) => setPromptCount(Number(e.target.value))}
                      className="w-full mt-1.5 p-2 bg-slate-950 border border-slate-700 rounded text-xs text-slate-100"
                    />
                  </label>
                  <label className="text-xs text-slate-200">
                    Maximum spend (USD)
                    <input
                      type="number"
                      min="0.000001"
                      max="100"
                      step="0.000001"
                      value={budget}
                      onChange={(e) => setBudget(e.target.value)}
                      className="w-full mt-1.5 p-2 bg-slate-950 border border-slate-700 rounded text-xs text-slate-100"
                    />
                  </label>
                </div>

                <div className="modal-policy my-3 flex items-center gap-2 p-3 rounded bg-emerald-950/20 border border-emerald-500/30 text-emerald-300 text-xs">
                  <LockKeyhole size={16} className="text-emerald-400 shrink-0" />
                  <span>
                    {confidential
                      ? "CONFIDENTIAL · trusted Nebius anchor only"
                      : "SYNTHETIC · verified multi-provider routing"}
                  </span>
                </div>

                {notice && (
                  <p role="alert" className="form-error text-xs text-red-400 my-2">
                    {notice}
                  </p>
                )}

                <button className="primary w-full mt-3 text-xs font-semibold py-2.5" disabled={!!busy} onClick={launch}>
                  {busy === "launch" ? (
                    <LoaderCircle size={16} className="spin" />
                  ) : (
                    <Zap size={16} />
                  )}{" "}
                  {SIMULATED ? "Launch demo batch" : "Launch batch"}
                </button>

                {jobResults && (
                  <button
                    type="button"
                    className="text-button w-full justify-center text-xs text-slate-400 hover:text-slate-200 mt-2 py-1"
                    onClick={() => setModalView("results")}
                  >
                    View previous batch results ({jobResults.length} items)
                  </button>
                )}
              </>
            )}
          </section>
        </div>
      )}
      <AttestationDrawer
        isOpen={isAttestationDrawerOpen}
        onClose={() => setIsAttestationDrawerOpen(false)}
        attestation={attestations[0] || null}
        promptResult={selectedPrompt}
        jobId={job?.job_id}
      />
    </div>
  );
}

function Metric({
  label,
  value,
  suffix,
  detail,
  icon,
  accent = false,
}: {
  label: string;
  value: string;
  suffix: string;
  detail: string;
  icon: React.ReactNode;
  accent?: boolean;
}) {
  return (
    <section className={`metric-card ${accent ? "accent" : ""}`}>
      <div className="metric-label text-xs font-semibold text-slate-300">
        {label}
        <span className={accent ? "text-emerald-400" : "text-sky-400"}>{icon}</span>
      </div>
      <div className="metric-value text-2xl font-semibold text-slate-100">
        {value}
        <small className="text-xs text-slate-400 ml-1.5">{suffix}</small>
      </div>
      <p className="text-xs text-slate-400 mt-1">{detail}</p>
    </section>
  );
}
