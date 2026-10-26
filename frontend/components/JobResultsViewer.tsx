"use client";
import React from "react";
import { ArrowRight, Download, Layers3, LoaderCircle } from "lucide-react";
import { usd, type Job } from "@/lib/types";

interface JobResultsViewerProps {
  job: Job | null;
  done: number;
  running: boolean;
  busy: string;
  onOpenModal: () => void;
  onDownload: () => void;
}

export default function JobResultsViewer({
  job,
  done,
  running,
  busy,
  onOpenModal,
  onDownload,
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
          <button
            className="secondary text-xs font-medium"
            disabled={running || !!busy}
            onClick={onDownload}
          >
            {busy === "results" ? (
              <LoaderCircle size={14} className="spin" />
            ) : (
              <Download size={14} />
            )}
            {" "}Results
          </button>
        </>
      ) : (
        <button className="text-button text-xs font-medium" onClick={onOpenModal}>
          Configure batch <ArrowRight size={15} />
        </button>
      )}
    </section>
  );
}
