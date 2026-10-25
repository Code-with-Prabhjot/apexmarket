"use client";
import React from "react";
import { FlaskConical } from "lucide-react";

export default function SimulationBanner() {
  return (
    <div className="simulation-banner" role="status">
      <FlaskConical size={14} />
      <strong>[SIMULATED DEMO FALLBACK ACTIVE]</strong>
      <span>Illustrative telemetry and payouts · repository benchmark shown separately</span>
    </div>
  );
}
