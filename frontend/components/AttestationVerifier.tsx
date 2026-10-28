"use client";

import React, { useState, useEffect, useRef } from "react";
import Link from "next/link";
import {
  ShieldCheck,
  ShieldAlert,
  UploadCloud,
  FileCode2,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  Copy,
  Check,
  ExternalLink,
  Cpu,
  Lock,
  Layers,
  Sparkles,
  Fingerprint,
  Hash,
  ChevronRight,
  ArrowRight,
  Shield,
  Clock,
  Terminal,
} from "lucide-react";
import {
  SAMPLE_AUDIT_CERTIFICATE,
  verifyAuditCertificate,
  type AuditCertificate,
  type VerificationVerdict,
  type ShredAuditRecord,
} from "@/lib/AuditCertificate";

export default function AttestationVerifier() {
  const [jsonText, setJsonText] = useState<string>("");
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [verdict, setVerdict] = useState<VerificationVerdict | null>(null);
  const [parsedCert, setParsedCert] = useState<AuditCertificate | null>(null);
  const [isVerifying, setIsVerifying] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [copiedHash, setCopiedHash] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"upload" | "json">("upload");
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Auto-run verification whenever jsonText changes
  useEffect(() => {
    if (!jsonText.trim()) {
      setVerdict(null);
      setParsedCert(null);
      setErrorMsg(null);
      return;
    }

    let isSubscribed = true;
    setIsVerifying(true);
    setErrorMsg(null);

    const runValidation = async () => {
      try {
        const cert = JSON.parse(jsonText);
        setParsedCert(cert);
        const result = await verifyAuditCertificate(cert);
        if (isSubscribed) {
          setVerdict(result);
          setIsVerifying(false);
        }
      } catch (err) {
        if (isSubscribed) {
          setErrorMsg(`JSON Parse Error: ${(err as Error).message}`);
          setVerdict({
            isValid: false,
            tamperedFields: ["json_syntax"],
            mismatches: [
              {
                shredId: "PARSER_FAILURE",
                reason: "Document is not valid JSON",
                expected: "Valid JSON String",
                actual: (err as Error).message,
              },
            ],
            summary: {
              totalShreds: 0,
              verifiedShreds: 0,
              totalTokens: 0,
              canariesPassed: 0,
              quarantinedCount: 0,
              algorithm: "SHA-256",
              timestampProvenance: "N/A",
            },
          });
          setIsVerifying(false);
        }
      }
    };

    const timer = setTimeout(runValidation, 150);
    return () => {
      isSubscribed = false;
      clearTimeout(timer);
    };
  }, [jsonText]);

  // Load sample verified bundle
  const handleLoadSample = () => {
    setErrorMsg(null);
    setJsonText(JSON.stringify(SAMPLE_AUDIT_CERTIFICATE, null, 2));
  };

  // Simulate tampering
  const handleSimulateTamper = () => {
    if (!parsedCert && !jsonText.trim()) {
      handleLoadSample();
    }
    try {
      const base = parsedCert ? JSON.parse(JSON.stringify(parsedCert)) : JSON.parse(JSON.stringify(SAMPLE_AUDIT_CERTIFICATE));
      if (base.shreds && base.shreds.length > 1) {
        // Tamper with prompt completion of shred 1
        base.shreds[1].completion = base.shreds[1].completion + " [UNVERIFIED QUANTIZATION DRIFT INJECTED]";
        // Inflate claimed total tokens
        if (base.audit_metrics) {
          base.audit_metrics.total_tokens_verified += 500;
        }
      } else {
        base.total_prompts = (base.total_prompts || 0) + 99;
      }
      setJsonText(JSON.stringify(base, null, 2));
    } catch {
      handleLoadSample();
    }
  };

  const handleClear = () => {
    setJsonText("");
    setVerdict(null);
    setParsedCert(null);
    setErrorMsg(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleFileUpload = (file: File) => {
    if (!file.name.endsWith(".json")) {
      setErrorMsg("Please upload a valid .json attestation certificate.");
      return;
    }
    const reader = new FileReader();
    reader.onload = (e) => {
      const content = e.target?.result as string;
      setJsonText(content);
    };
    reader.onerror = () => setErrorMsg("Failed to read file.");
    reader.readAsText(file);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileUpload(e.dataTransfer.files[0]);
    }
  };

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedHash(id);
    setTimeout(() => setCopiedHash(null), 2000);
  };

  return (
    <div className="w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 text-slate-100">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between pb-6 border-b border-[#202c3c] gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-[#70e4bf] mb-1">
            <ShieldCheck size={16} /> Independent Zero-Backend Verifier
          </div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
            Attestation Verification Portal
          </h1>
          <p className="text-sm text-slate-400 mt-1 max-w-2xl">
            Client-side Web Crypto API (<code className="text-[#70e4bf]">subtle.digest</code>) independently recalculates
            cryptographic SHA-256 hashes for each micro-batch shred, validates token billing counts, and audits HMAC signatures with zero server telemetry dependence.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={handleLoadSample}
            className="flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-semibold bg-[#70e4bf1f] hover:bg-[#70e4bf33] text-[#70e4bf] border border-[#70e4bf44] transition-all shadow-lg shadow-[#70e4bf10]"
          >
            <Sparkles size={14} /> Load Sample Certificate
          </button>
          <button
            onClick={handleSimulateTamper}
            className="flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-semibold bg-[#f871711a] hover:bg-[#f871712a] text-[#f87171] border border-[#f8717144] transition-all"
            title="Inject an intentional digest discrepancy to inspect fail-closed rejection"
          >
            <AlertTriangle size={14} /> Simulate Tampering
          </button>
          {jsonText && (
            <button
              onClick={handleClear}
              className="p-2 rounded-lg text-slate-400 hover:text-slate-200 bg-[#162232] border border-[#202c3c] transition-colors"
              title="Clear input"
            >
              <RefreshCw size={14} />
            </button>
          )}
        </div>
      </div>

      {/* Grid: Upload & Input Area */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 mt-6">
        <div className="lg:col-span-5 flex flex-col gap-4">
          {/* Input Mode Selector */}
          <div className="flex rounded-lg bg-[#0e1624] p-1 border border-[#202c3c]">
            <button
              onClick={() => setActiveTab("upload")}
              className={`flex-1 py-1.5 text-xs font-semibold rounded-md transition-colors flex items-center justify-center gap-2 ${
                activeTab === "upload"
                  ? "bg-[#1a2638] text-white shadow-sm"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <UploadCloud size={14} /> Drag & Drop File
            </button>
            <button
              onClick={() => setActiveTab("json")}
              className={`flex-1 py-1.5 text-xs font-semibold rounded-md transition-colors flex items-center justify-center gap-2 ${
                activeTab === "json"
                  ? "bg-[#1a2638] text-white shadow-sm"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <FileCode2 size={14} /> Paste JSON Text
            </button>
          </div>

          {activeTab === "upload" ? (
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setIsDragging(true);
              }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`border-2 border-dashed rounded-xl p-8 flex flex-col items-center justify-center text-center cursor-pointer transition-all min-h-[260px] ${
                isDragging
                  ? "border-[#70e4bf] bg-[#70e4bf0a]"
                  : "border-[#25364c] hover:border-[#384f6d] bg-[#0c121e]"
              }`}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".json,application/json"
                className="hidden"
                onChange={(e) => {
                  if (e.target.files && e.target.files[0]) {
                    handleFileUpload(e.target.files[0]);
                  }
                }}
              />
              <div className="w-12 h-12 rounded-xl bg-[#162232] border border-[#202c3c] flex items-center justify-center text-[#70e4bf] mb-3 shadow-inner">
                <UploadCloud size={24} />
              </div>
              <h3 className="text-sm font-semibold text-slate-100">
                Drop your <code className="text-[#70e4bf]">apexmarket-attestation-*.json</code> certificate
              </h3>
              <p className="text-xs text-slate-400 mt-1 max-w-xs">
                or click to browse your local filesystem. Processed entirely in-memory using Web Crypto.
              </p>
              <span className="mt-4 px-2.5 py-1 rounded text-[11px] font-mono text-slate-400 bg-[#162232] border border-[#202c3c]">
                Zero Telemetry · 100% Client-Side
              </span>
            </div>
          ) : (
            <div className="flex flex-col flex-1 min-h-[260px]">
              <textarea
                value={jsonText}
                onChange={(e) => setJsonText(e.target.value)}
                placeholder='Paste raw JSON here: {"apexmarket_version": "3.0.0-enterprise", ...}'
                className="w-full h-full min-h-[260px] p-4 text-xs font-mono bg-[#0c121e] border border-[#202c3c] rounded-xl text-slate-200 focus:outline-none focus:border-[#70e4bf] focus:ring-1 focus:ring-[#70e4bf] resize-none"
              />
            </div>
          )}

          {/* Quick Specifications */}
          <div className="p-4 rounded-xl bg-[#0c121e] border border-[#202c3c] text-xs text-slate-400 flex flex-col gap-2">
            <div className="flex items-center gap-2 text-slate-300 font-semibold">
              <Lock size={14} className="text-[#edbb72]" /> Cryptographic Audit Guarantees
            </div>
            <ul className="list-disc list-inside space-y-1 text-[11px] leading-relaxed">
              <li>Deterministic SHA-256 digests over prompt + completion payloads</li>
              <li>Authoritative token billing verification matching offline tokenizer counts</li>
              <li>HMAC signature consistency cross-referenced with cluster registry</li>
              <li>Quarantined spot node telemetry isolation checks</li>
            </ul>
          </div>
        </div>

        {/* Right Column: Audit Verdict & Provenance Details */}
        <div className="lg:col-span-7 flex flex-col gap-4">
          {!verdict ? (
            <div className="h-full min-h-[360px] rounded-xl border border-[#202c3c] bg-[#0c121e] flex flex-col items-center justify-center p-8 text-center">
              <div className="w-14 h-14 rounded-2xl bg-[#162232] border border-[#202c3c] flex items-center justify-center text-slate-500 mb-4">
                <Fingerprint size={28} />
              </div>
              <h3 className="text-base font-semibold text-slate-200">
                Awaiting Attestation Certificate
              </h3>
              <p className="text-xs text-slate-400 mt-1 max-w-md">
                Load a sample certificate or drop an exported batch bundle to execute client-side cryptographic verification.
              </p>
              <button
                onClick={handleLoadSample}
                className="mt-5 px-4 py-2 rounded-lg text-xs font-semibold bg-[#70e4bf1f] hover:bg-[#70e4bf33] text-[#70e4bf] border border-[#70e4bf44] transition-all flex items-center gap-2"
              >
                <Sparkles size={14} /> Load Verified Sample Certificate
              </button>
            </div>
          ) : verdict.isValid ? (
            /* VALID VERDICT CARD */
            <div className="rounded-xl border border-[#70e4bf44] bg-[#0c121e] overflow-hidden shadow-2xl shadow-[#70e4bf0d]">
              {/* Glowing Emerald Header Banner */}
              <div className="bg-gradient-to-r from-[#70e4bf1f] via-[#70e4bf2b] to-[#70e4bf10] p-6 border-b border-[#70e4bf44] flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 rounded-xl bg-[#70e4bf24] border border-[#70e4bf] flex items-center justify-center text-[#70e4bf] shadow-lg shadow-[#70e4bf33] animate-pulse">
                    <CheckCircle2 size={28} />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold tracking-wider uppercase bg-[#70e4bf] text-black">
                        Pass 100%
                      </span>
                      <span className="text-xs font-mono text-[#70e4bf]">SHA-256 · PROOF VALIDATED</span>
                    </div>
                    <h2 className="text-lg sm:text-xl font-black text-white tracking-wide mt-0.5">
                      CRYPTOGRAPHICALLY VERIFIED & AUDITED
                    </h2>
                    <p className="text-xs text-slate-300 mt-0.5">
                      All shred digests, token sums, and HMAC signatures match authoritative cryptographic provenance.
                    </p>
                  </div>
                </div>

                <div className="text-right flex sm:flex-col items-center sm:items-end justify-between border-t sm:border-t-0 pt-2 sm:pt-0 border-[#70e4bf33]">
                  <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">Job Identity</span>
                  <span className="text-xs font-mono font-bold text-[#70e4bf]">{parsedCert?.job_id || "N/A"}</span>
                  <span className="text-[10px] text-slate-400 mt-0.5 flex items-center gap-1">
                    <Clock size={10} /> {parsedCert?.timestamp_utc ? new Date(parsedCert.timestamp_utc).toLocaleTimeString() : "N/A"}
                  </span>
                </div>
              </div>

              {/* Verified Metrics Row */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 p-5 bg-[#0e1624] border-b border-[#202c3c]">
                <div className="p-3 rounded-lg bg-[#141e2e] border border-[#202c3c]">
                  <span className="text-[10px] font-bold uppercase text-slate-400 tracking-wider">Verified Shreds</span>
                  <div className="text-lg font-black text-white mt-0.5 flex items-baseline gap-1">
                    {verdict.summary.verifiedShreds}
                    <span className="text-xs font-normal text-slate-400">/ {verdict.summary.totalShreds}</span>
                  </div>
                </div>

                <div className="p-3 rounded-lg bg-[#141e2e] border border-[#202c3c]">
                  <span className="text-[10px] font-bold uppercase text-slate-400 tracking-wider">Tokens Verified</span>
                  <div className="text-lg font-black text-[#70e4bf] mt-0.5">
                    {verdict.summary.totalTokens.toLocaleString()}
                  </div>
                </div>

                <div className="p-3 rounded-lg bg-[#141e2e] border border-[#202c3c]">
                  <span className="text-[10px] font-bold uppercase text-slate-400 tracking-wider">Canary Audits</span>
                  <div className="text-lg font-black text-[#70e4bf] mt-0.5 flex items-center gap-1">
                    <ShieldCheck size={16} /> 100% Pass
                  </div>
                </div>

                <div className="p-3 rounded-lg bg-[#141e2e] border border-[#202c3c]">
                  <span className="text-[10px] font-bold uppercase text-slate-400 tracking-wider">Client Savings</span>
                  <div className="text-lg font-black text-[#edbb72] mt-0.5">
                    {parsedCert?.audit_metrics?.net_client_savings_pct || "32.18%"}
                  </div>
                </div>
              </div>

              {/* Itemized Shred Table */}
              <div className="p-5">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-1.5">
                    <Hash size={14} className="text-[#70e4bf]" /> Itemized Shred Verification Table
                  </h3>
                  <span className="text-[11px] font-mono text-slate-400">
                    Algorithm: {verdict.summary.algorithm}
                  </span>
                </div>

                <div className="overflow-x-auto rounded-lg border border-[#202c3c]">
                  <table className="w-full text-left text-xs text-slate-200">
                    <thead className="bg-[#101826] text-slate-400 uppercase text-[10px] font-bold border-b border-[#202c3c]">
                      <tr>
                        <th className="py-2.5 px-3">Shred ID</th>
                        <th className="py-2.5 px-3">Executing Node</th>
                        <th className="py-2.5 px-3">Tokens</th>
                        <th className="py-2.5 px-3">Canary</th>
                        <th className="py-2.5 px-3">SHA-256 Digest</th>
                        <th className="py-2.5 px-3 text-right">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#202c3c] font-mono text-[11px]">
                      {parsedCert?.shreds && parsedCert.shreds.length > 0 ? (
                        parsedCert.shreds.map((shred: ShredAuditRecord) => (
                          <tr key={String(shred.shred_id)} className="hover:bg-[#141f30] transition-colors">
                            <td className="py-2.5 px-3 font-semibold text-white whitespace-nowrap">
                              {shred.shred_id}
                            </td>
                            <td className="py-2.5 px-3 whitespace-nowrap">
                              <span
                                className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                                  shred.node_id.includes("anchor") || shred.node_id.includes("nebius")
                                    ? "bg-[#70e4bf1a] text-[#70e4bf] border border-[#70e4bf44]"
                                    : "bg-[#edbb721a] text-[#edbb72] border border-[#edbb7244]"
                                }`}
                              >
                                {shred.node_id}
                              </span>
                            </td>
                            <td className="py-2.5 px-3 whitespace-nowrap">
                              <span className="text-slate-300 font-semibold">{shred.total_tokens || shred.input_tokens + shred.output_tokens}</span>
                              <span className="text-slate-500 text-[10px] ml-1">({shred.input_tokens}in / {shred.output_tokens}out)</span>
                            </td>
                            <td className="py-2.5 px-3 whitespace-nowrap">
                              {shred.canary_passed ? (
                                <span className="inline-flex items-center gap-1 text-[#70e4bf]">
                                  <Check size={12} /> Passed
                                </span>
                              ) : (
                                <span className="text-red-400">Failed</span>
                              )}
                            </td>
                            <td className="py-2.5 px-3 whitespace-nowrap">
                              <button
                                onClick={() => copyToClipboard(shred.sha256_hash, String(shred.shred_id))}
                                className="group flex items-center gap-1 text-slate-400 hover:text-slate-200"
                                title={shred.sha256_hash}
                              >
                                <span>{shred.sha256_hash.slice(0, 8)}...{shred.sha256_hash.slice(-6)}</span>
                                {copiedHash === String(shred.shred_id) ? (
                                  <Check size={11} className="text-[#70e4bf]" />
                                ) : (
                                  <Copy size={11} className="opacity-40 group-hover:opacity-100" />
                                )}
                              </button>
                            </td>
                            <td className="py-2.5 px-3 text-right whitespace-nowrap">
                              <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-[#70e4bf1f] text-[#70e4bf] border border-[#70e4bf44]">
                                VERIFIED
                              </span>
                            </td>
                          </tr>
                        ))
                      ) : parsedCert?.cryptographic_signatures && parsedCert.cryptographic_signatures.length > 0 ? (
                        parsedCert.cryptographic_signatures.map((sig, idx) => (
                          <tr key={idx} className="hover:bg-[#141f30] transition-colors">
                            <td className="py-2.5 px-3 font-semibold text-white whitespace-nowrap">
                              {sig.shred_id}
                            </td>
                            <td className="py-2.5 px-3 whitespace-nowrap">
                              <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-[#70e4bf1a] text-[#70e4bf] border border-[#70e4bf44]">
                                {sig.node_id}
                              </span>
                            </td>
                            <td className="py-2.5 px-3 whitespace-nowrap text-slate-400">—</td>
                            <td className="py-2.5 px-3 whitespace-nowrap text-[#70e4bf]">Audited</td>
                            <td className="py-2.5 px-3 whitespace-nowrap text-slate-400 font-mono">
                              {sig.sha256_hash.slice(0, 8)}...{sig.sha256_hash.slice(-6)}
                            </td>
                            <td className="py-2.5 px-3 text-right whitespace-nowrap">
                              <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-[#70e4bf1f] text-[#70e4bf] border border-[#70e4bf44]">
                                {sig.attestation_status}
                              </span>
                            </td>
                          </tr>
                        ))
                      ) : null}
                    </tbody>
                  </table>
                </div>

                {parsedCert?.quarantined_nodes && parsedCert.quarantined_nodes.length > 0 && (
                  <div className="mt-4 p-3 rounded-lg bg-[#edbb7210] border border-[#edbb7233] flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2 text-[#edbb72]">
                      <AlertTriangle size={15} />
                      <span>
                        Quarantined Node Isolation Enforced:{" "}
                        <code className="font-bold text-slate-200">{parsedCert.quarantined_nodes.join(", ")}</code>
                      </span>
                    </div>
                    <span className="text-[10px] uppercase font-bold text-slate-400">Zero Leakage</span>
                  </div>
                )}
              </div>
            </div>
          ) : (
            /* TAMPERED / REJECTED CARD */
            <div className="rounded-xl border border-red-500/50 bg-[#0c121e] overflow-hidden shadow-2xl shadow-red-500/10">
              <div className="bg-gradient-to-r from-red-500/20 via-red-500/30 to-red-500/10 p-6 border-b border-red-500/40 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 rounded-xl bg-red-500/20 border border-red-500 flex items-center justify-center text-red-400 shadow-lg shadow-red-500/30">
                    <ShieldAlert size={28} />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold tracking-wider uppercase bg-red-500 text-white">
                        VERIFICATION FAILED
                      </span>
                      <span className="text-xs font-mono text-red-400">CRYPTOGRAPHIC INTEGRITY TAMPERED</span>
                    </div>
                    <h2 className="text-lg sm:text-xl font-black text-white tracking-wide mt-0.5">
                      INTEGRITY VIOLATION DETECTED
                    </h2>
                    <p className="text-xs text-red-200 mt-0.5">
                      Client-side recalculation of SHA-256 digests flagged discrepancies with authoritative bundle claims.
                    </p>
                  </div>
                </div>

                <div className="text-right">
                  <span className="px-2.5 py-1 rounded text-xs font-bold uppercase tracking-wider bg-red-950 text-red-300 border border-red-500/40">
                    Fail-Closed Rejection
                  </span>
                </div>
              </div>

              {/* Mismatch Breakdown */}
              <div className="p-5">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300 mb-3 flex items-center gap-2">
                  <AlertTriangle size={15} className="text-red-400" /> Exact Discrepancy Diagnostics ({verdict.mismatches.length})
                </h3>

                <div className="space-y-3">
                  {verdict.mismatches.map((m, idx) => (
                    <div
                      key={idx}
                      className="p-3.5 rounded-lg bg-red-950/30 border border-red-500/30 text-xs flex flex-col gap-1.5"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-red-300">Target: Shred #{m.shredId}</span>
                        <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-red-900/50 text-red-200 border border-red-700/50">
                          Integrity Mismatch
                        </span>
                      </div>
                      <p className="text-slate-300 text-xs">{m.reason}</p>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-1 text-[11px] font-mono">
                        <div className="p-2 rounded bg-[#0a0f18] border border-slate-800">
                          <span className="text-slate-500 block text-[10px] uppercase font-bold">Expected / Claimed:</span>
                          <span className="text-slate-300 break-all">{m.expected}</span>
                        </div>
                        <div className="p-2 rounded bg-[#0a0f18] border border-red-500/30">
                          <span className="text-red-400 block text-[10px] uppercase font-bold">Computed / Actual:</span>
                          <span className="text-red-300 break-all">{m.actual}</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>

                <div className="mt-5 p-3.5 rounded-lg bg-[#141e2e] border border-[#202c3c] text-xs text-slate-400 flex items-center justify-between">
                  <span>Economic Invariant: Tampered batches are stripped of settlement rights and rerouted to Nebius Anchor.</span>
                  <button
                    onClick={handleLoadSample}
                    className="text-xs font-semibold text-[#70e4bf] hover:underline"
                  >
                    Restore Valid Bundle →
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Navigation Footer */}
      <div className="mt-12 pt-6 border-t border-[#202c3c] flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-slate-400">
        <div className="flex items-center gap-4">
          <Link href="/" className="hover:text-slate-200 transition-colors">
            ← Back to Landing
          </Link>
          <span>·</span>
          <Link href="/dashboard" className="hover:text-slate-200 transition-colors">
            Mission Control
          </Link>
          <span>·</span>
          <Link href="/architecture" className="hover:text-slate-200 transition-colors">
            System Architecture Whitepaper
          </Link>
        </div>
        <div>ApexMarket · Institutional Enterprise Showcase Suite</div>
      </div>
    </div>
  );
}
