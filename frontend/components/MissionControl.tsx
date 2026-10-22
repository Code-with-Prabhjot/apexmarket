"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { Activity, ArrowDownRight, ArrowRight, Check, ChevronRight, CircleDollarSign, Command, Cpu, Download, FlaskConical, Layers3, LoaderCircle, LockKeyhole, Radio, RotateCcw, ShieldCheck, Terminal, Wallet, Zap } from "lucide-react";
import BenchmarkChart from "./BenchmarkChart";
import { demoProviders, demoSnapshot, settleDemo } from "@/lib/simulation";
import { nodeState, usd, type Benchmark, type Job, type Provider, type Snapshot } from "@/lib/types";
import { summarize } from "@/lib/benchmarks";
const Topology = dynamic(() => import("./Topology"), { ssr: false, loading: () => <div className="topology loading">Initializing network…</div> });
const SIMULATED = process.env.NEXT_PUBLIC_MOCK_FALLBACK === "true";
type Log = { id: number; time: string; text: string; tone: string };
type Attestation = { status: string; node_id: string; canary_pass_rate: number | null; anchor_nll_score: number | null; nemotron_judge_score: number | null; server_hmac_attestation: string | null };
async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api/backend/${path}`, { cache: "no-store", ...options });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : `Request failed (${response.status})`);
  return data;
}
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
  const [prompt, setPrompt] = useState("Explain how verified inference protects a batch workload in one sentence.");
  const [promptCount, setPromptCount] = useState(50);
  const [budget, setBudget] = useState("1.00");
  const [adminKey, setAdminKey] = useState("");
  const [modal, setModal] = useState(false);
  const [lastBatch, setLastBatch] = useState<{ batch_id: string; status: string } | null>(null);
  const [retry, setRetry] = useState(0);
  const eventId = useRef(0);
  const simulatedDone = useRef(0);
  const jobRef = useRef(job); jobRef.current = job;
  const settlementKey = useRef<string | null>(null);
  const addLog = useCallback((text: string, tone = "info") => {
    const id = ++eventId.current;
    setLogs(previous => [{ id, time: new Date().toLocaleTimeString("en-GB", { hour12: false }), text, tone }, ...previous].slice(0, 40));
  }, []);

  const initialized = useRef(false);
  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;
    if (!SIMULATED) {
      settlementKey.current = sessionStorage.getItem("apex-payout-retry");
      const saved = sessionStorage.getItem("apex-last-payout");
      if (saved) { try { setLastBatch(JSON.parse(saved)); } catch { sessionStorage.removeItem("apex-last-payout"); } }
    }
    addLog(SIMULATED ? "Simulation initialized. Confidential routing enabled." : "Mission Control initialized. Waiting for engine telemetry.");
  }, [addLog]);
  useEffect(() => {
    let stopped = false;
    const load = async () => {
      try { const r = await fetch("/api/benchmarks", { cache: "no-store" }); if (!r.ok) throw new Error("Could not read benchmark CSV"); const b = await r.json(); if (!stopped) setBenchmark(b); }
      catch (e) { if (!stopped) setNotice((e as Error).message); }
    };
    void load(); const timer = setInterval(load, 30000);
    return () => { stopped = true; clearInterval(timer); };
  }, []);

  useEffect(() => {
    if (SIMULATED) return;
    let stopped = false, loading = false;
    const load = async () => {
      if (loading) return; loading = true;
      try {
        const [registry, telemetry] = await Promise.allSettled([api<Provider[]>("nodes"), api<Array<{ node_id: string; tokens_per_sec: number; p95_ttft_ms: number }>>("telemetry")]);
        if (stopped) return;
        if (registry.status === "rejected") throw registry.reason;
        const metrics = telemetry.status === "fulfilled" ? telemetry.value : [];
        setProviders(registry.value.map(p => ({ ...p, ...metrics.find(t => t.node_id === p.node_id) })));
        setHttpError(telemetry.status === "rejected" ? "Rolling throughput is temporarily unavailable." : "");
      } catch (e) { if (!stopped) setHttpError((e as Error).message); }
      finally { loading = false; }
    };
    void load(); const timer = setInterval(load, 5000);
    return () => { stopped = true; clearInterval(timer); };
  }, [retry]);

  useEffect(() => {
    if (SIMULATED) return;
    let disposed = false, socket: WebSocket | undefined, timer: ReturnType<typeof setTimeout>, delay = 1000, lastMessage = 0;
    function connect() {
      if (disposed) return;
      setConnection("Connecting");
      try {
        socket = new WebSocket(process.env.NEXT_PUBLIC_WS_URL || `${location.protocol === "https:" ? "wss" : "ws"}://${location.hostname}:8000/ws/telemetry`);
        socket.onopen = () => { if (disposed) return; lastMessage = Date.now(); delay = 1000; setConnection("Live"); };
        socket.onmessage = event => {
          if (disposed) return;
          try {
            const data = JSON.parse(event.data);
            if (!Array.isArray(data.nodes) || typeof data.jobs !== "object" || !Number.isFinite(data.ts)) throw new Error("Invalid snapshot");
            lastMessage = Date.now(); setSnapshot(data);
          } catch { setConnection("Invalid telemetry"); }
        };
        socket.onerror = () => socket?.close();
        socket.onclose = () => { if (disposed) return; setConnection("Reconnecting"); timer = setTimeout(connect, delay); delay = Math.min(delay * 2, 10000); };
      } catch { setConnection("Disconnected"); timer = setTimeout(connect, delay); }
    }
    connect(); const watchdog = setInterval(() => { if (lastMessage && Date.now() - lastMessage > 5000) socket?.close(); }, 2000);
    return () => { disposed = true; clearTimeout(timer); clearInterval(watchdog); socket?.close(); };
  }, [retry]);

  useEffect(() => {
    if (!SIMULATED) return;
    let tick = 0;
    const update = () => {
      tick++;
      const current = jobRef.current;
      if (current?.status === "RUNNING") {
        simulatedDone.current = Math.min(current.total_prompts, simulatedDone.current + Math.max(1, Math.ceil(current.total_prompts / 45)));
        if (simulatedDone.current === current.total_prompts) {
          setJob(j => j ? { ...j, status: "COMPLETED", actual_settled_cost_micros: 923, platform_fee_micros: 43, total_makespan_ms: 45000 } : j);
          setProviders(previous => previous.map((p, i) => {
            const earned = current.sensitivity === "CONFIDENTIAL" ? i === 0 : i === 1;
            return earned ? { ...p, withdrawable_micros: p.withdrawable_micros + 923 } : p;
          }));
          addLog("Demo batch completed. Outputs reassembled in prompt order; verified earnings credited.", "success");
        }
      }
      setSnapshot(demoSnapshot(tick, current?.status === "RUNNING" ? current.sensitivity === "CONFIDENTIAL" : confidential, slashed, current?.total_prompts ?? 0, simulatedDone.current, current?.job_id));
    };
    update(); const timer = setInterval(update, 1000);
    return () => clearInterval(timer);
  }, [confidential, slashed, addLog]);

  useEffect(() => {
    if (SIMULATED || !job || !["QUEUED", "RUNNING"].includes(job.status)) return;
    let stopped = false, loading = false;
    const update = async () => {
      if (loading) return; loading = true;
      try {
        const [current, evidence] = await Promise.all([api<Job>(`jobs/${job.job_id}`), api<Attestation[]>(`jobs/${job.job_id}/attestations`)]);
        if (!stopped) { setJob(current); setAttestations(evidence); if (!["RUNNING", "QUEUED"].includes(current.status)) addLog(`Batch ${current.status.toLowerCase()}. Cost ${usd(current.actual_settled_cost_micros)}.`, current.status === "COMPLETED" ? "success" : "warning"); }
      } catch (e) { if (!stopped) setNotice((e as Error).message); }
      finally { loading = false; }
    };
    void update(); const timer = setInterval(update, 1500);
    return () => { stopped = true; clearInterval(timer); };
  }, [job?.job_id, job?.status, addLog]);

  useEffect(() => {
    if (SIMULATED || !adminKey || !lastBatch || lastBatch.status !== "SUBMITTED_PENDING") return;
    let stopped = false, loading = false;
    const reconcile = async () => {
      if (loading) return; loading = true;
      try {
        const receipt = await api<{ batch_id: string; status: string }>(`ledger/payouts/${lastBatch.batch_id}/reconcile`, { method: "POST", headers: { "Content-Type": "application/json", "X-Admin-Key": adminKey }, body: "{}" });
        if (!stopped && receipt.status !== lastBatch.status) {
          setLastBatch(receipt); sessionStorage.setItem("apex-last-payout", JSON.stringify(receipt));
          addLog(`PayPal Sandbox payout ${receipt.status.toLowerCase()}.`, receipt.status === "COMPLETED" ? "success" : "warning");
          setRetry(n => n + 1);
        }
      } catch (e) { if (!stopped) setNotice((e as Error).message); }
      finally { loading = false; }
    };
    void reconcile(); const timer = setInterval(reconcile, 5000);
    return () => { stopped = true; clearInterval(timer); };
  }, [adminKey, lastBatch?.batch_id, lastBatch?.status, addLog]);

  const displaySnapshot: Snapshot = {
    ...snapshot,
    nodes: providers.map(provider => {
      const live = snapshot.nodes.find(node => node.node_id === provider.node_id) ?? {
        node_id: provider.node_id, status: "ACTIVE", active_requests: 0,
        p50_ttft_ms: 0, p95_ttft_ms: 0, error_rate: 0,
      };
      return attestations.some(a => a.node_id === provider.node_id && a.status === "VERIFIED_FAIL_REROUTED")
        ? { ...live, status: "SLASHED" } : live;
    }),
  };

  const totalWithdrawable = providers.reduce((n, p) => n + p.withdrawable_micros, 0);
  const pending = providers.reduce((n, p) => n + p.payout_pending_micros, 0);
  const held = providers.reduce((n, p) => n + p.pending_probation_micros, 0);
  const throughput = snapshot.nodes.reduce((sum, p) => sum + (p.tokens_per_sec ?? providers.find(n => n.node_id === p.node_id)?.tokens_per_sec ?? 0), 0);
  const progress = job ? snapshot.jobs[job.job_id] : undefined;
  const done = job?.status === "COMPLETED" ? job.total_prompts : progress?.done ?? 0;
  const running = !!job && ["RUNNING", "QUEUED"].includes(job.status);
  const graphConfidential = running ? job.sensitivity === "CONFIDENTIAL" : confidential;
  const baseline = summarize(benchmark?.rows ?? [], "DEFAULT_PROVIDER_BASELINE");
  const apex = summarize(benchmark?.rows ?? [], "APEXMARKET_VERIFIED_ROUTER");
  const savings = baseline && apex ? (1 - apex.cost / baseline.cost) * 100 : null;

  function togglePrivacy() {
    setConfidential(value => !value);
    addLog(confidential ? "Next batch classified SYNTHETIC. Verified spot routing enabled." : "Next batch classified CONFIDENTIAL. Trusted anchor only.", "success");
  }
  async function launch() {
    const lines = prompt.split("\n").filter(p => p.trim());
    const micros = Math.round(Number(budget) * 1_000_000);
    if (!/^\d+(?:\.\d{1,6})?$/.test(budget) || !lines.length || lines.some(p => p.length > 32000) || !Number.isInteger(promptCount) || promptCount < 1 || promptCount > 5000 || !Number.isSafeInteger(micros) || micros < 1 || micros > 100000000) { setNotice("Use 1–5,000 prompts, up to 32,000 characters each, and a budget from $0.000001 to $100."); return; }
    setBusy("launch"); setNotice(""); setAttestations([]);
    try {
      const sensitivity = confidential ? "CONFIDENTIAL" : "SYNTHETIC";
      if (SIMULATED) {
        simulatedDone.current = 0;
        setJob({ job_id: crypto.randomUUID(), status: "RUNNING", sensitivity, total_prompts: promptCount, actual_settled_cost_micros: 0, platform_fee_micros: 0, reserved_escrow_micros: micros });
      } else {
        setJob(await api<Job>("jobs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sensitivity, prompts: Array.from({ length: promptCount }, (_, i) => ({ prompt_index: i, content: lines[i % lines.length] })), max_tokens_per_prompt: 128, max_cost_ceiling_micros: micros, makespan_sla_seconds: 120 }) }));
      }
      addLog(`${SIMULATED ? "Demo" : "Live"} batch submitted · ${promptCount} prompts · ${sensitivity}.`, "success"); setModal(false);
    } catch (e) { setNotice((e as Error).message); }
    finally { setBusy(""); }
  }
  async function injectDrift() {
    setBusy("drift"); setNotice("");
    try {
      if (!SIMULATED) await api("demo/drift", { method: "POST", headers: { "Content-Type": "application/json", "X-Admin-Key": adminKey }, body: JSON.stringify({ degraded: !slashed }) });
      setSlashed(v => !v);
      addLog(slashed ? "Mock provider restored to honest outputs." : (SIMULATED ? "Demo drift detected. Corrupted shreds rejected; prompts rerouted to anchor." : "Mock provider set to degraded output. Subsequent batch attestations show verification results."), slashed ? "success" : "warning");
    } catch (e) { setNotice((e as Error).message); }
    finally { setBusy(""); }
  }
  async function settle() {
    setBusy("settle"); setNotice("");
    try {
      if (SIMULATED) {
        const next = settleDemo(providers); setProviders(next);
        const amount = next.reduce((n, p) => n + p.payout_pending_micros, 0) - pending;
        addLog(`Simulated payout submitted · ${usd(amount, 2)} · sub-cent remainder retained.`, "success");
        setNotice(`Simulated sandbox batch submitted: ${usd(amount, 2)}. No money was moved.`);
      } else {
        settlementKey.current ??= crypto.randomUUID();
        sessionStorage.setItem("apex-payout-retry", settlementKey.current);
        const receipt = await api<{ batch_id: string; status: string; total_amount_micros: number }>("ledger/settle-now", { method: "POST", headers: { "Content-Type": "application/json", "X-Admin-Key": adminKey, "Idempotency-Key": settlementKey.current }, body: "{}" });
        addLog(`PayPal Sandbox · ${receipt.status} · ${usd(receipt.total_amount_micros, 2)} · ${receipt.batch_id}`, "success");
        setNotice(`Sandbox payout ${receipt.status.toLowerCase()}: ${usd(receipt.total_amount_micros, 2)}. Receipt ${receipt.batch_id}`);
        settlementKey.current = null; sessionStorage.removeItem("apex-payout-retry");
        setLastBatch(receipt); sessionStorage.setItem("apex-last-payout", JSON.stringify(receipt));
        setRetry(r => r + 1);
      }
    } catch (e) { setNotice((e as Error).message); }
    finally { setBusy(""); }
  }
  async function downloadResults() {
    if (!job) return;
    setBusy("results");
    try {
      const results = SIMULATED ? Array.from({ length: job.total_prompts }, (_, i) => ({ prompt_index: i, status: "SIMULATED", output_text: "Verified inference audits each batch before releasing node payment." })) : await api<Array<{ prompt_index: number }>>(`jobs/${job.job_id}/results`);
      const url = URL.createObjectURL(new Blob([JSON.stringify(results.sort((a, b) => a.prompt_index - b.prompt_index), null, 2)], { type: "application/json" }));
      const link = document.createElement("a"); link.href = url; link.download = `${SIMULATED ? "simulated-" : ""}${job.job_id}.json`; link.click(); URL.revokeObjectURL(url);
    } catch (e) { setNotice((e as Error).message); }
    finally { setBusy(""); }
  }
  const failedEvidence = attestations.some(a => a.status === "VERIFIED_FAIL_REROUTED");
  const rejected = SIMULATED ? slashed : failedEvidence;
  const tiers = [
    { name: "Authoritative token billing", detail: "Local tokenizer · provider-independent", value: SIMULATED && job ? "Active" : attestations.length ? "Recorded" : "Ready" },
    { name: "Rotated canary probes", detail: "4% dynamic challenge injection", value: SIMULATED && slashed ? "Rejected" : attestations.some(a => a.canary_pass_rate !== null) ? "Recorded" : "Ready" },
    { name: "Secret anchor sampling", detail: "5% reference comparison", value: SIMULATED && job ? "Demo" : "Policy" },
    { name: "Anchor logprob scoring", detail: "Teacher-forcing negative log-likelihood", value: SIMULATED && slashed ? "Demo spike" : attestations.some(a => a.anchor_nll_score !== null) ? "Recorded" : "Policy" },
    { name: "Nemotron semantic judge", detail: "Borderline output arbitration", value: SIMULATED && slashed ? "Demo reject" : attestations.some(a => a.nemotron_judge_score !== null) ? "Recorded" : "Policy" },
  ];
  return <div className="app-shell">
    <aside className="sidebar"><a href="#overview" className="brand-mark" aria-label="ApexMarket home"><Zap size={24} fill="currentColor" /></a><a href="#overview" className="nav-icon selected" aria-label="Overview"><Command size={21} /></a><a href="#network" className="nav-icon" aria-label="Network"><Layers3 size={21} /></a><a href="#benchmarks" className="nav-icon" aria-label="Benchmarks"><Activity size={21} /></a><a href="#settlement" className="nav-icon" aria-label="Settlement"><Wallet size={21} /></a><div className="sidebar-bottom"><span className="environment-dot" /><span>DEV</span></div></aside>
    <div className="workspace" id="overview">
      {SIMULATED && <div className="simulation-banner"><FlaskConical size={14} /><strong>[SIMULATED DEMO FALLBACK ACTIVE]</strong><span>Illustrative telemetry and payouts · repository benchmark shown separately</span></div>}
      <header className="topbar"><a href="#overview" className="wordmark">apex<span>market</span><span className="version">/ mission control</span></a><div className="topbar-right"><span className={`connection ${connection === "Live" || SIMULATED ? "healthy" : ""}`}><span className="dot" />{connection}</span><span className="environment">SANDBOX</span><span className="avatar">AM</span></div></header>
      <main>
        <div className="page-heading"><div><div className="eyebrow">INFERENCE OPERATIONS <ChevronRight size={12} /> OVERVIEW</div><h1>Mission Control<span>.</span></h1><p>Route intelligently. Verify every shred. Settle with confidence.</p></div><button className="primary" onClick={() => setModal(true)} disabled={running || !!busy}><Zap size={15} /> Launch batch <ArrowRight size={15} /></button></div>
        {(notice || httpError) && <div className="notice" role="status"><span>{notice || httpError}</span><button aria-label="Dismiss message" onClick={() => { setNotice(""); setHttpError(""); }}>×</button></div>}
        {!SIMULATED && !["Live", "Connecting"].includes(connection) && <div className="connection-warning">Telemetry reconnecting. Last snapshot is retained. <button onClick={() => setRetry(r => r + 1)}>Reconnect</button></div>}
        <div className="metrics-grid"><Metric label="VERIFIED COST SAVINGS" value={savings === null ? "—" : `${savings.toFixed(2)}%`} suffix="vs. single provider" icon={<ArrowDownRight size={18} />} detail="Repository benchmark · includes audit compute" accent /><Metric label="NETWORK THROUGHPUT" value={Math.round(throughput).toLocaleString()} suffix="tok/s" icon={<Activity size={18} />} detail={SIMULATED ? "Simulated · updates every second" : "Rolling provider telemetry"} /><Metric label="ACTIVE PROVIDERS" value={`${providers.filter(p => p.is_active && nodeState(displaySnapshot.nodes.find(n => n.node_id === p.node_id), p.is_active) !== "slashed").length}`.padStart(2, "0")} suffix={`/ ${providers.length.toString().padStart(2, "0")} registered`} icon={<Cpu size={18} />} detail={graphConfidential ? "Trusted anchor routing enforced" : "Verified multi-provider routing"} /><Metric label="WITHDRAWABLE BALANCE" value={usd(totalWithdrawable, 2)} suffix="USD" icon={<CircleDollarSign size={18} />} detail={`${totalWithdrawable.toLocaleString()} integer micro-dollars`} /></div>
        <div className="main-grid"><section className="panel network-panel" id="network"><div className="panel-heading"><div><div className="eyebrow"><Radio size={14} /> NETWORK TOPOLOGY</div><h2>One router. Verified compute.</h2></div><span className="pill"><span className="dot optimal" /> {SIMULATED ? "DEMO NETWORK" : "LIVE NETWORK"}</span></div><div className="privacy-strip"><div className="privacy-icon"><LockKeyhole size={17} /></div><div><strong>Confidential air-gap</strong><span>{confidential ? "ON · All new workloads stay on the trusted anchor" : "OFF · New synthetic workloads may use spot compute"}</span></div><button className={`toggle ${confidential ? "on" : ""}`} role="switch" aria-label="Confidential air-gap" aria-checked={confidential} onClick={togglePrivacy} disabled={running}><span /></button></div><Topology providers={providers} snapshot={displaySnapshot} confidential={graphConfidential} /><div className="graph-footer"><div><span><i className="dot optimal" /> Optimal</span><span><i className="dot slow" /> Slow</span><span><i className="dot slashed" /> Slashed</span></div><span>Edge width ∝ throughput</span></div></section>
          <section className="panel verification-panel" id="verification"><div className="panel-heading"><div><div className="eyebrow"><ShieldCheck size={14} /> PROOF BEFORE PAYMENT</div><h2>Verification pipeline</h2></div><span className="pill muted">5 TIERS</span></div><div className="tier-list">{tiers.map((tier, i) => <div className={`tier ${tier.value.includes("reject") || tier.value === "Rejected" || tier.value.includes("spike") ? "failed" : ""}`} key={tier.name}><span className="tier-index">0{i + 1}</span><div><strong>{tier.name}</strong><span>{tier.detail}</span></div><b>{tier.value}</b></div>)}</div><div className={`verification-note ${rejected ? "danger" : ""}`}><ShieldCheck size={19} /><div><strong>{rejected ? "Corrupted shred rejected" : "Every payout starts with proof"}</strong><p>{rejected ? "Failed output earns no payout. Unverified prompts route to the trusted anchor." : "Only verified work earns a ledger credit. Attestations protect the settlement boundary."}</p></div></div><button className={`chaos-button ${slashed ? "restore" : ""}`} onClick={injectDrift} disabled={!!busy || confidential || (!SIMULATED && !adminKey)}>{busy === "drift" ? <LoaderCircle size={15} className="spin" /> : slashed ? <RotateCcw size={15} /> : <FlaskConical size={15} />}{slashed ? "Restore honest provider" : "Inject INT4 quantization drift"}<span>{SIMULATED ? "DEMO" : "MOCK"}</span></button><p className="fine-print">{confidential ? "Disable the air-gap to test a synthetic workload on spot compute." : "Chaos changes only the configured local mock provider."}</p></section></div>
        <section className="panel batch-panel" id="batch"><div className="batch-title"><Layers3 size={19} /><div><strong>{job ? `Batch ${job.job_id.slice(0, 8)}` : "Ready for your next batch"}</strong><span>{job ? `${job.total_prompts} prompts · ${job.sensitivity} · ${job.status}` : "Privacy defaults to CONFIDENTIAL. Submit up to 5,000 prompts."}</span></div></div>{job ? <><div className="batch-progress"><div><span>{done} / {job.total_prompts} complete</span><b>{Math.round(done / job.total_prompts * 100)}%</b></div><progress max={job.total_prompts} value={done} /></div><div className="batch-cost">{usd(job.actual_settled_cost_micros)}<small>verified cost</small></div><button className="secondary" disabled={running || !!busy} onClick={downloadResults}><Download size={14} /> Results</button></> : <button className="text-button" onClick={() => setModal(true)}>Configure batch <ArrowRight size={15} /></button>}</section>
        <div className="bottom-grid"><BenchmarkChart benchmark={benchmark} /><section className="panel settlement-panel" id="settlement"><div className="panel-heading"><div><div className="eyebrow"><Wallet size={14} /> SETTLEMENT ENGINE</div><h2>Small units. Exact accounting.</h2></div><span className="paypal-mark">Pay<span>Pal</span></span></div><div className="balance-display"><span>Available for settlement</span><strong>{usd(totalWithdrawable, 6)}<small>USD</small></strong><p>{totalWithdrawable.toLocaleString()} micros <span>·</span> integer precision</p></div><div className="ledger-breakdown"><div><span>Probation escrow</span><b>{usd(held)}</b></div><div><span>Payout pending</span><b>{usd(pending)}</b></div><div><span>Sub-cent carry after payout</span><b>{usd(providers.reduce((n, p) => n + p.withdrawable_micros % 10000, 0))}</b></div></div>{!SIMULATED && <label className="admin-label">Sandbox admin key<input type="password" autoComplete="off" value={adminKey} onChange={e => setAdminKey(e.target.value)} placeholder="Enter session key" /></label>}<button className="settle-button" onClick={settle} disabled={!!busy || providers.every(p => p.withdrawable_micros < 10000) || (!SIMULATED && !adminKey)}>{busy === "settle" ? <LoaderCircle size={16} className="spin" /> : <Wallet size={16} />} Settle now (Sandbox) <ArrowRight size={16} /></button>{lastBatch && <p className="payout-receipt">Batch {lastBatch.batch_id.slice(0, 8)} · {lastBatch.status.replaceAll("_", " ")}</p>}<p className="fine-print"><LockKeyhole size={11} /> {SIMULATED ? "Simulated payouts · no external money movement" : "Sandbox only · idempotent payouts · $0.01 minimum"}</p></section></div>
        <section className="panel activity-panel"><div className="activity-heading"><div className="eyebrow"><Terminal size={14} /> EVENT STREAM</div><span>{SIMULATED ? "SIMULATED" : "SESSION EVENTS"}</span></div><div className="event-list" aria-live="polite" aria-relevant="additions">{logs.slice(0, 5).map(log => <div className={`event ${log.tone}`} key={log.id}><time>{log.time}</time><span className="dot" /><p>{log.text}</p></div>)}</div></section>
        <footer><span><Zap size={12} /> APEXMARKET <b>/</b> Verified inference infrastructure</span><span>CONFIDENTIAL by default <span className="dot optimal" /></span></footer>
      </main>
    </div>
    {modal && <div className="modal-backdrop" onClick={e => { if (e.target === e.currentTarget && !busy) setModal(false); }}><section role="dialog" aria-modal="true" aria-labelledby="batch-title" className="batch-modal" onKeyDown={e => {
      if (e.key === "Escape") setModal(false);
      if (e.key === "Tab") {
        const focusable = e.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled), input, textarea, select');
        const first = focusable[0], last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    }}><div className="panel-heading"><div><div className="eyebrow">NEW WORKLOAD</div><h2 id="batch-title">Launch a verified batch</h2></div><button className="close-button" aria-label="Close batch configuration" onClick={() => setModal(false)}>×</button></div><label>Prompt templates <small>One per line, repeated to fill the batch</small><textarea autoFocus rows={4} value={prompt} onChange={e => setPrompt(e.target.value)} /></label><div className="form-row"><label>Prompt count<input type="number" min="1" max="5000" value={promptCount} onChange={e => setPromptCount(Number(e.target.value))} /></label><label>Maximum spend (USD)<input type="number" min="0.000001" max="100" step="0.000001" value={budget} onChange={e => setBudget(e.target.value)} /></label></div><div className="modal-policy"><LockKeyhole size={16} /><span>{confidential ? "CONFIDENTIAL · trusted Nebius anchor only" : "SYNTHETIC · verified multi-provider routing"}</span></div>{notice && <p role="alert" className="form-error">{notice}</p>}<button className="primary" disabled={!!busy} onClick={launch}>{busy === "launch" ? <LoaderCircle size={16} className="spin" /> : <Zap size={16} />} {SIMULATED ? "Launch demo batch" : "Launch batch"}</button></section></div>}
  </div>;
}
function Metric({ label, value, suffix, detail, icon, accent = false }: { label: string; value: string; suffix: string; detail: string; icon: React.ReactNode; accent?: boolean }) {
  return <section className={`metric-card ${accent ? "accent" : ""}`}><div className="metric-label">{label}<span>{icon}</span></div><div className="metric-value">{value}<small>{suffix}</small></div><p>{detail}</p></section>;
}
