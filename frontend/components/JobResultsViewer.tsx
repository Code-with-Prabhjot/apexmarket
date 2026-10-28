"use client";
import React from "react";
import { ArrowRight, Download, Layers3, LoaderCircle, ShieldCheck, Key } from "lucide-react";
import { usd, type Job } from "@/lib/types";

interface JobResultsViewerProps {
  job: Job | null;
  done: number;
  running: boolean;
  busy: string;
  onOpenModal: () => void;
  onDownload: () => void;
  onExportAudit?: () => void;
  onInspectProof?: () => void;
}

export default function JobResultsViewer({
  job,
  done,
  running,
  busy,
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
                onClick={onInspectProof}
                title="Inspect 5-tier cryptographic proof breakdown"
              >
                <Key size={13} />
                {" "}Inspect Proof
              </button>
            )}
          </div>
        </>
      ) : (
        <button className="text-button text-xs font-medium" onClick={onOpenModal}>
          Configure batch <ArrowRight size={15} />
        </button>
      )}
    </section>
  );
}
