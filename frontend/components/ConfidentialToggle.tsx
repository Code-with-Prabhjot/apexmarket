"use client";
import React from "react";
import { LockKeyhole } from "lucide-react";

interface ConfidentialToggleProps {
  confidential: boolean;
  onToggle: () => void;
  disabled?: boolean;
}

export default function ConfidentialToggle({
  confidential,
  onToggle,
  disabled = false,
}: ConfidentialToggleProps) {
  return (
    <div className="privacy-strip">
      <div className="privacy-icon">
        <LockKeyhole size={17} />
      </div>
      <div>
        <strong>Confidential air-gap</strong>
        <span>
          {confidential
            ? "ON · All new workloads stay on the trusted anchor"
            : "OFF · New synthetic workloads may use spot compute"}
        </span>
      </div>
      <button
        className={`toggle ${confidential ? "on" : ""}`}
        role="switch"
        aria-label="Confidential air-gap"
        aria-checked={confidential}
        onClick={onToggle}
        disabled={disabled}
      >
        <span />
      </button>
    </div>
  );
}
