"use client";
import React from "react";
import { ArrowRight, Download, Layers3, LoaderCircle, ShieldCheck, Key, Cpu } from "lucide-react";
import { usd, getProviderBadgeInfo, type Job } from "@/lib/types";
import type { PromptResultItem } from "@/lib/api";

interface JobResultsViewerProps {
  job: Job | null;
  done: number;
  running: boolean;
  busy: string;
  results?: PromptResultItem[] | null;
  onOpenModal: () => void;
  onDownload: () => void;
  onExportAudit?: () => void;
  onInspectProof?: (prompt?: PromptResultItem) => void;
}

export default function JobResultsViewer({
  job,
  done,
  running,
  busy,
  results,
  onOpenModal,
  onDownload,
  onExportAudit,
  onInspectProof,
}: JobResultsViewerProps) {
  return (
    <section className="panel batch-panel" id="batch">
      <div className="batch-title">
        <Layers3 size={19} className="text-emerald-400" />
        <div>
          <strong className="text-sm font-semibold text-slate-100 block">
            {job ? `Batch ${job.job_id.slice(0, 8)}` : "Ready for your next batch"}
          </strong>
          <span className="text-xs text-slate-300 block mt-1">
            {job
              ? `${job.total_prompts} prompts · ${job.sensitivity} · ${job.status}`
              : "Privacy defaults to CONFIDENTIAL. Submit up to 5,000 prompts."}
          </span>
        </div>
      </div>
      {job ? (
        <>
          <div className="batch-progress">
            <div className="flex justify-between text-xs text-slate-300 mb-1">
              <span>
                {done} / {job.total_prompts} complete
              </span>
              <b className="text-xs font-semibold text-emerald-400">
                {job.total_prompts > 0
                  ? Math.round((done / job.total_prompts) * 100)
                  : 0}
                %
              </b>
            </div>
            <progress max={job.total_prompts} value={done} />
          </div>
          <div className="batch-cost text-sm font-mono font-medium text-slate-100">
            {usd(job.actual_settled_cost_micros)}
            <small className="block text-xs text-slate-400 mt-0.5">verified cost</small>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <button
              className="secondary text-xs font-medium"
              disabled={running || !!busy}
              onClick={onDownload}
              title="Download raw reassembled prompt results JSON"
            >
              {busy === "results" ? (
                <LoaderCircle size={14} className="spin" />
              ) : (
                <Download size={14} />
              )}
              {" "}Results
            </button>

            {onExportAudit && (
              <button
                className="secondary text-xs font-medium border-[#70e4bf55] text-[#70e4bf] hover:bg-[#70e4bf15]"
                disabled={running || !!busy}
                onClick={onExportAudit}
                title="Export signed cryptographic audit certificate"
              >
                <ShieldCheck size={14} />
                {" "}Attestation Bundle
              </button>
            )}

            {onInspectProof && (
              <button
                className="secondary text-xs font-medium text-amber-300 border-amber-500/40 hover:bg-amber-500/10"
                disabled={running}
                onClick={() => onInspectProof()}
                title="Inspect 5-tier cryptographic proof breakdown"
              >
                <Key size={13} />
                {" "}Inspect Proof
              </button>
            )}
          </div>

          {/* Executing Provider Breakdown on Completed Prompt Rows */}
          {results && results.length > 0 && job.status === "COMPLETED" && (
            <div className="mt-4 pt-3 border-t border-slate-800/80 space-y-2">
              <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
                <span className="font-semibold text-slate-200 flex items-center gap-1.5">
                  <Cpu size={14} className="text-[#70e4bf]" /> Executing Provider Node Telemetry
                </span>
                <span className="font-mono text-[11px] text-slate-400">
                  Showing {Math.min(results.length, 3)} of {results.length} shreds
                </span>
              </div>
              <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                {results.slice(0, 3).map((item) => {
                  const badgeInfo = getProviderBadgeInfo(item.executing_node_id, item.prompt_index);
                  const inTokens = item.input_tokens ?? 32;
                  const outTokens = item.output_tokens ?? 64;
                  const totalTokens = inTokens + outTokens;
                  const shredMicroCost = inTokens * badgeInfo.inRateMicros + outTokens * badgeInfo.outRateMicros;

                  return (
                    <div
                      key={item.prompt_index}
                      className="p-2.5 rounded-lg bg-slate-900/90 border border-slate-800/90 text-xs space-y-1.5"
                    >
                      <div className="flex items-center justify-between gap-2 flex-wrap">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-mono font-semibold text-emerald-400">
                            Prompt #{item.prompt_index + 1}
                          </span>
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
                        {onInspectProof && (
                          <button
                            type="button"
                            className="px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-500/15 text-amber-300 border border-amber-500/40 hover:bg-amber-500/25 transition-colors"
                            onClick={() => onInspectProof(item)}
                          >
                            Inspect Proof
                          </button>
                        )}
                      </div>
                      <p className="text-slate-300 text-[11px] line-clamp-1 font-sans">
                        {item.output_text}
                      </p>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </>
      ) : (
        <button className="text-button text-xs font-medium" onClick={onOpenModal}>
          Configure batch <ArrowRight size={15} />
        </button>
      )}
    </section>
  );
}
