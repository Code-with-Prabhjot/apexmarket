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
        <Layers3 size={19} />
        <div>
          <strong>
            {job ? `Batch ${job.job_id.slice(0, 8)}` : "Ready for your next batch"}
          </strong>
          <span>
            {job
              ? `${job.total_prompts} prompts · ${job.sensitivity} · ${job.status}`
              : "Privacy defaults to CONFIDENTIAL. Submit up to 5,000 prompts."}
          </span>
        </div>
      </div>
      {job ? (
        <>
          <div className="batch-progress">
            <div>
              <span>
                {done} / {job.total_prompts} complete
              </span>
              <b>
                {job.total_prompts > 0
                  ? Math.round((done / job.total_prompts) * 100)
                  : 0}
                %
              </b>
            </div>
            <progress max={job.total_prompts} value={done} />
          </div>
          <div className="batch-cost">
            {usd(job.actual_settled_cost_micros)}
            <small>verified cost</small>
          </div>
          <button
            className="secondary"
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
        <button className="text-button" onClick={onOpenModal}>
          Configure batch <ArrowRight size={15} />
        </button>
      )}
    </section>
  );
}
