"use client";
import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import Link from "next/link";
import {
  ArrowRight,
  ChevronRight,
  CircleDollarSign,
  Cpu,
  Layers3,
  ShieldCheck,
  Wallet,
  TrendingDown,
  Zap,
  Anchor,
  Scale,
  Gauge,
  CheckCircle2,
} from "lucide-react";
import "./landing.css";

function Reveal({ children, d = 0 }: { children: ReactNode; d?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { el.classList.add("in"); io.disconnect(); } }, { threshold: 0.15 });
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return <div ref={ref} className="lp-rv" style={{ "--d": `${d}s` } as CSSProperties}>{children}</div>;
}

function Network() {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const c = ref.current!, x = c.getContext("2d")!;
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let w = 0, h = 0, raf = 0;
    const m = { x: -999, y: -999 };
    const P = Array.from({ length: 56 }, () => ({ x: Math.random(), y: Math.random(), vx: (Math.random() - .5) * 4e-4, vy: (Math.random() - .5) * 4e-4 }));
    const fit = () => { w = c.width = c.offsetWidth; h = c.height = c.offsetHeight; };
    const move = (e: MouseEvent) => { const r = c.getBoundingClientRect(); m.x = e.clientX - r.left; m.y = e.clientY - r.top; };
    const tick = () => {
      x.clearRect(0, 0, w, h);
      for (const p of P) { p.x = (p.x + p.vx + 1) % 1; p.y = (p.y + p.vy + 1) % 1; }
      for (let i = 0; i < P.length; i++) {
        const a = P[i], ax = a.x * w, ay = a.y * h;
        for (let j = i + 1; j < P.length; j++) {
          const dx = ax - P[j].x * w, dy = ay - P[j].y * h, d = Math.hypot(dx, dy);
          if (d < 150) { x.strokeStyle = `rgba(112,228,191,${(1 - d / 150) * .22})`; x.beginPath(); x.moveTo(ax, ay); x.lineTo(P[j].x * w, P[j].y * h); x.stroke(); }
        }
        const near = Math.hypot(ax - m.x, ay - m.y) < 170;
        x.fillStyle = near ? "#70e4bf" : "rgba(112,228,191,.5)";
        x.beginPath(); x.arc(ax, ay, near ? 3.2 : 2, 0, 7); x.fill();
        if (near) { x.strokeStyle = "rgba(237,187,114,.35)"; x.beginPath(); x.moveTo(ax, ay); x.lineTo(m.x, m.y); x.stroke(); }
      }
      raf = requestAnimationFrame(tick);
    };
    fit(); tick();
    addEventListener("resize", fit); addEventListener("mousemove", move);
    return () => { cancelAnimationFrame(raf); removeEventListener("resize", fit); removeEventListener("mousemove", move); };
  }, []);
  return <canvas ref={ref} aria-hidden />;
}

function Typed({ words }: { words: string[] }) {
  const [t, setT] = useState("");
  useEffect(() => {
    let i = 0, n = 0, del = false, id: ReturnType<typeof setTimeout>;
    const run = () => {
      const w = words[i];
      n += del ? -1 : 1; setT(w.slice(0, n));
      let ms = del ? 45 : 90;
      if (!del && n === w.length) { del = true; ms = 1400; }
      else if (del && n === 0) { del = false; i = (i + 1) % words.length; ms = 300; }
      id = setTimeout(run, ms);
    };
    run();
    return () => clearTimeout(id);
  }, [words]);
  return <em>{t}</em>;
}

const problems = [
  { i: TrendingDown, big: "1.3× – 1.6×", t: "Same model, different price", p: "Providers publish different per-token rates for identical open-weight models. A fixed default provider leaves that gap unclaimed." },
  { i: ShieldCheck, big: "Silent drift", t: "Same name, different quality", p: "Quantization and serving differences can change outputs with no flag in the API. Cheap capacity is only useful if it is checked." },
  { i: CircleDollarSign, big: "$0.25", t: "Fees eat tiny payments", p: "A payout fee can exceed the work itself. ApexMarket keeps its own ledger and settles in batches." },
];

const pillars = [
  {
    icon: Anchor,
    tag: "Reference Anchor",
    title: "Nebius Nemotron-3-Nano Anchor",
    desc: "Unquantized reference anchor (nvidia/nemotron-3-nano-30b-a3b) running at temperature 0.0 with 5% secret-seeded CSPRNG sampling and logprob drift detection to catch silent provider model substitutions.",
    badge: "5% CSPRNG Audit",
  },
  {
    icon: ShieldCheck,
    tag: "Verification Engine",
    title: "5-Tier Proof Before Payment",
    desc: "Every batch shred passes offline tokenizer billing, rotated canary probes, reference anchor sampling, cross-entropy logprob scoring, and a Nemotron semantic arbiter before payment escrow is released.",
    badge: "Deterministic Escrow",
  },
  {
    icon: Scale,
    tag: "Cost Arbitrage",
    title: "32.18% Cost Arbitrage",
    desc: "Empirically validated multi-provider cost arbitrage drops per-query costs from $0.001361 to $0.000923, delivering 32.18% net savings even after accounting for full 9% verification audit overhead.",
    badge: "Verified 32.18% Savings",
  },
];

const steps = [
  { i: Layers3, t: "Shred", p: "Your batch is split into small shreds. Secrets and personal data are redacted before anything leaves, and jobs default to Confidential, which stays on the trusted Nebius anchor.", c: ["PII redaction", "Confidential by default", "Spend caps"] },
  { i: Zap, t: "Route", p: "A scheduler fills the cheapest healthy providers first, within each provider's capacity, and uses live speed probes to adapt.", c: ["Price-aware", "Capacity limits", "Failover"] },
  { i: ShieldCheck, t: "Verify", p: "Every shred passes five checks before it counts: local token billing, canary probes, anchor sampling, logprob scoring and a Nemotron judge.", c: ["5 tiers", "Nemotron judge", "Fail closed"] },
  { i: Wallet, t: "Settle", p: "Prepaid top-ups sit in escrow. Only verified work is paid, through PayPal batch payouts. Failed shreds earn nothing.", c: ["PayPal escrow", "Batch payouts", "Idempotent ledger"] },
];

const tiers = [
  ["Local tokenizer billing", "Token counts come from a local tokenizer, never the provider's own usage numbers. Outputs are scanned for injection payloads and unsafe artifacts."],
  ["Rotated canary probes", "Hidden prompts with known answers are mixed into each shred. Two or more failures fail the shred and slash its earnings."],
  ["Anchor reference sampling", "A secret-seeded 5% of real prompts also run on the trusted Nebius anchor at temperature 0, then get compared."],
  ["Logprob scoring", "The anchor scores each candidate output. A spike in negative log-likelihood points to heavy quantization or model substitution."],
  ["Nemotron judge", "A Nemotron model arbitrates borderline shreds that the other checks cannot settle."],
];

const nodes = [["Nebius anchor", 78, "$0.06"], ["Spot node A", 52, "$0.04"], ["Spot node B", 40, "$0.03"]] as const;

function Flow() {
  const [s, setS] = useState(0);
  const [auto, setAuto] = useState(true);
  useEffect(() => { if (!auto) return; const id = setTimeout(() => setS(v => (v + 1) % steps.length), 5000); return () => clearTimeout(id); }, [s, auto]);
  const Cur = steps[s];
  return (
    <div className="lp-flow">
      <div className="lp-steps">
        {steps.map((x, k) => (
          <button key={x.t} className={`lp-step ${k === s ? "on" : ""}`} onClick={() => { setS(k); setAuto(false); }}>
            <b>{k + 1}</b>{x.t}{k === s && auto && <i />}
          </button>
        ))}
      </div>
      <div className="lp-stage"><div key={s}><Cur.i size={30} color="var(--green)" style={{ marginBottom: 18 }} /><h3>{Cur.t}</h3><p>{Cur.p}</p><div className="lp-chips">{Cur.c.map(c => <span key={c}>{c}</span>)}</div></div></div>
    </div>
  );
}

function CostCalculator() {
  const [prompts, setPrompts] = useState(50000);
  // Default Provider Baseline: $0.001361 per prompt ($0.10/M in, $0.38/M out)
  // ApexMarket Verified: $0.000923 per prompt ($0.06/M in, $0.24/M out + 9% audit overhead)
  const defaultCost = (prompts * 0.001361);
  const apexCost = (prompts * 0.000923);
  const totalSavings = defaultCost - apexCost;
  const platformFee = totalSavings * 0.10; // 10% platform take rate
  const netClientSavings = totalSavings - platformFee;
  const savingsPct = 32.18;

  const presets = [10000, 50000, 100000, 500000];

  return (
    <div className="lp-calc">
      <div className="lp-calc-header">
        <div>
          <h3>Interactive Cost Arbitrage Calculator</h3>
          <p>Verified against empirical benchmark data on identical open-weight Nemotron workloads.</p>
        </div>
        <div className="lp-calc-presets">
          {presets.map(p => (
            <button
              key={p}
              className={`lp-preset-btn ${prompts === p ? "active" : ""}`}
              onClick={() => setPrompts(p)}
            >
              {(p / 1000).toLocaleString()}k prompts
            </button>
          ))}
        </div>
      </div>

      <div className="lp-calc-slider-wrap">
        <label htmlFor="prompt-volume">
          Batch Volume: <strong>{prompts.toLocaleString()} prompts</strong>
        </label>
        <input
          id="prompt-volume"
          type="range"
          min="5000"
          max="1000000"
          step="5000"
          value={prompts}
          onChange={(e) => setPrompts(Number(e.target.value))}
          className="lp-slider"
        />
        <div className="lp-slider-labels">
          <span>5k</span>
          <span>250k</span>
          <span>500k</span>
          <span>750k</span>
          <span>1,000k</span>
        </div>
      </div>

      <div className="lp-calc-grid">
        <div className="lp-calc-card baseline">
          <span className="lp-calc-tag">Default Provider</span>
          <div className="lp-calc-cost">${defaultCost.toFixed(2)}</div>
          <p className="lp-calc-rate">$0.10 / $0.38 per 1M tokens</p>
          <ul className="lp-calc-specs">
            <li><span>Single provider lock-in</span></li>
            <li><span>No quality verification</span></li>
            <li><span>Fixed retail pricing</span></li>
          </ul>
        </div>

        <div className="lp-calc-card apex">
          <div className="lp-calc-badge-row">
            <span className="lp-calc-tag highlight">ApexMarket Verified</span>
            <span className="lp-calc-badge-pill">{savingsPct}% SAVINGS</span>
          </div>
          <div className="lp-calc-cost highlight">${apexCost.toFixed(2)}</div>
          <p className="lp-calc-rate">$0.06 / $0.24 per 1M tokens</p>
          <ul className="lp-calc-specs">
            <li><CheckCircle2 size={14} color="var(--green)" /> <span>5-Tier Proof Before Payment</span></li>
            <li><CheckCircle2 size={14} color="var(--green)" /> <span>Nebius Nemotron-3-Nano Anchor</span></li>
            <li><CheckCircle2 size={14} color="var(--green)" /> <span>898 TPS · 52ms TTFT · 0.00% Errors</span></li>
          </ul>
        </div>

        <div className="lp-calc-card savings">
          <span className="lp-calc-tag green">Net Retained Savings</span>
          <div className="lp-calc-cost savings-val">+${netClientSavings.toFixed(2)}</div>
          <p className="lp-calc-rate">After 10% platform performance fee (${platformFee.toFixed(2)})</p>
          <div className="lp-calc-cta-row">
            <Link className="lp-btn" href="/dashboard">
              Launch Mission Control <ArrowRight size={16} />
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}

function Demo() {
  const ref = useRef<HTMLDivElement>(null);
  const [on, setOn] = useState(false);
  const [bad, setBad] = useState(false);
  useEffect(() => {
    const el = ref.current!;
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setOn(true); io.disconnect(); } }, { threshold: 0.3 });
    io.observe(el); return () => io.disconnect();
  }, []);
  return (
    <div className="lp-demo" ref={ref}>
      {nodes.map(([n, v, pay], k) => {
        const hit = bad && k === 2;
        return (
          <div key={n} className={`lp-node ${hit ? "bad" : ""}`}>
            <b>{n}</b>
            <div className="lp-bar"><i style={{ width: on ? `${hit ? 12 : v}%` : 0 }} /></div>
            <em>{hit ? "slashed · $0.00" : `verified · ${pay}`}</em>
          </div>
        );
      })}
      <div className="lp-row">
        <button className="lp-btn ghost" onClick={() => setBad(v => !v)}>{bad ? "Restore node B" : "Inject a bad node"}</button>
        <small>Illustration only. Live benchmark data is audited in CSV provenance.</small>
      </div>
    </div>
  );
}

export default function Landing() {
  const [solid, setSolid] = useState(false);
  const [open, setOpen] = useState(0);
  useEffect(() => { const f = () => setSolid(scrollY > 20); f(); addEventListener("scroll", f); return () => removeEventListener("scroll", f); }, []);
  const glow = (e: React.MouseEvent<HTMLElement>) => { const r = e.currentTarget.getBoundingClientRect(); e.currentTarget.style.setProperty("--mx", `${e.clientX - r.left}px`); e.currentTarget.style.setProperty("--my", `${e.clientY - r.top}px`); };

  return (
    <main className="lp">
      <header className={`lp-nav ${solid ? "solid" : ""}`}>
        <span className="lp-word"><span>Apex</span><span>Market</span></span>
        <nav>
          <a href="#highlights">Highlights</a>
          <a href="#arbitrage">Cost Arbitrage</a>
          <a href="#how">How it works</a>
          <a href="#verify">Verification</a>
          <Link className="lp-btn" href="/dashboard" style={{ padding: "9px 18px" }}>
            Launch Mission Control
          </Link>
        </nav>
      </header>

      <section className="lp-hero">
        <Network />
        <div>
          <div className="lp-pill"><i />Nebius · NVIDIA Nemotron-3-Nano · PayPal Escrow</div>
          <h1>Inference that is <Typed words={["verified.", "cheaper.", "paid on proof."]} /></h1>
          <p className="lp-sub">
            ApexMarket splits batch AI workloads across spot providers, verifies every shred against a trusted Nebius Nemotron reference anchor, and releases payment only when proof succeeds.
          </p>
          <div className="lp-cta">
            <Link className="lp-btn" href="/dashboard">
              Launch Mission Control <ArrowRight size={18} />
            </Link>
            <a className="lp-btn ghost" href="#arbitrage">
              Compare 32.18% Arbitrage
            </a>
          </div>
        </div>
        <span className="lp-scroll" />
      </section>

      {/* Feature Highlights Section */}
      <section className="lp-sec" id="highlights">
        <Reveal>
          <div className="lp-eyebrow">Architectural Pillars</div>
          <h2>Proof Before Payment with Reference Anchor Security</h2>
          <p className="lp-lead">
            Built on unquantized reference models, deterministic cryptographic verification, and sub-cent double-entry ledger balance conservation.
          </p>
        </Reveal>
        <div className="lp-grid">
          {pillars.map((item, k) => (
            <Reveal key={item.title} d={k * 0.12}>
              <div className="lp-card lp-pillar-card" onMouseMove={glow}>
                <div className="lp-card-top">
                  <item.icon size={28} className="lp-pillar-icon" />
                  <span className="lp-card-pill">{item.badge}</span>
                </div>
                <div className="lp-eyebrow" style={{ marginTop: 14, marginBottom: 6 }}>{item.tag}</div>
                <h3>{item.title}</h3>
                <p>{item.desc}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* Interactive Cost Arbitrage Comparison */}
      <section className="lp-sec" id="arbitrage" style={{ paddingTop: 0 }}>
        <Reveal>
          <div className="lp-eyebrow">Empirical Cost Arbitrage</div>
          <h2>32.18% Verified Cost Savings Without Quality Loss</h2>
          <p className="lp-lead">
            Measured across 3 empirical benchmark runs on identical NVIDIA Nemotron open-weight models. High throughput and 52ms TTFT with zero vendor lock-in.
          </p>
        </Reveal>
        <Reveal d={0.1}>
          <CostCalculator />
        </Reveal>
      </section>

      <section className="lp-sec" id="problem" style={{ paddingTop: 0 }}>
        <Reveal><div className="lp-eyebrow">The problem</div><h2>Cheap capacity exists. Trusting it is the hard part.</h2><p className="lp-lead">Routing by price alone is easy. Knowing the answer is right, and paying fairly for it, is what ApexMarket adds.</p></Reveal>
        <div className="lp-grid">
          {problems.map((p, k) => (
            <Reveal key={p.t} d={k * 0.12}><div className="lp-card" onMouseMove={glow}><p.i size={26} /><div className="lp-big">{p.big}</div><h3>{p.t}</h3><p>{p.p}</p></div></Reveal>
          ))}
        </div>
      </section>

      <section className="lp-sec" id="how" style={{ paddingTop: 0 }}>
        <Reveal><div className="lp-eyebrow">How it works</div><h2>Four steps from raw batch to verified payout.</h2></Reveal>
        <Reveal d={0.1}><Flow /></Reveal>
      </section>

      <section className="lp-sec" id="verify" style={{ paddingTop: 0 }}>
        <Reveal><div className="lp-eyebrow">Proof before payment</div><h2>Five checks stand between a node and its money.</h2><p className="lp-lead">Open a tier to see what it catches. Try the demo to see what a failed node earns.</p></Reveal>
        <div className="lp-tiers">
          {tiers.map(([t, p], k) => (
            <Reveal key={t} d={k * 0.07}>
              <div className={`lp-tier ${open === k ? "open" : ""}`}>
                <button onClick={() => setOpen(open === k ? -1 : k)}><span>TIER {k + 1}</span>{t}<ChevronRight size={18} /></button>
                <div><p>{p}</p></div>
              </div>
            </Reveal>
          ))}
        </div>
        <Reveal d={0.1}><Demo /></Reveal>
      </section>

      <section className="lp-final">
        <Reveal>
          <Cpu size={36} color="var(--green)" style={{ marginBottom: 18 }} />
          <h2>See the swarm run on real data.</h2>
          <Link className="lp-btn" href="/dashboard" style={{ fontSize: "15px", padding: "16px 32px" }}>
            Launch Mission Control <ArrowRight size={18} />
          </Link>
        </Reveal>
      </section>
      <p className="lp-foot">ApexMarket · Verified inference. Measured savings. Proof before payment.</p>
    </main>
  );
}
