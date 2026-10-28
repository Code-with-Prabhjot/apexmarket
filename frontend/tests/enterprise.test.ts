import assert from "node:assert/strict";
import { test } from "node:test";
import { INDUSTRY_BATCH_PRESETS } from "../lib/batchPresets";
import { exportAuditCertificate } from "../lib/AuditCertificate";
import type { Job } from "../lib/types";

test("INDUSTRY_BATCH_PRESETS has 3 enterprise presets with correct configurations", () => {
  assert.equal(INDUSTRY_BATCH_PRESETS.length, 3);

  const sec10k = INDUSTRY_BATCH_PRESETS.find((p) => p.id === "sec-10k")!;
  assert.ok(sec10k);
  assert.equal(sec10k.promptCount, 50);
  assert.equal(sec10k.prompts.length, 50);
  assert.equal(sec10k.sensitivity, "PUBLIC");

  const hipaa = INDUSTRY_BATCH_PRESETS.find((p) => p.id === "hipaa-medical")!;
  assert.ok(hipaa);
  assert.equal(hipaa.promptCount, 25);
  assert.equal(hipaa.prompts.length, 25);
  assert.equal(hipaa.sensitivity, "CONFIDENTIAL");

  const canary = INDUSTRY_BATCH_PRESETS.find((p) => p.id === "code-canary")!;
  assert.ok(canary);
  assert.equal(canary.promptCount, 100);
  assert.equal(canary.prompts.length, 100);
  assert.equal(canary.sensitivity, "SYNTHETIC");
});

test("exportAuditCertificate generates compliant enterprise attestation JSON", () => {
  const mockJob: Job = {
    job_id: "job-test-enterprise-42",
    status: "COMPLETED",
    sensitivity: "CONFIDENTIAL",
    total_prompts: 50,
    actual_settled_cost_micros: 5926,
    reserved_escrow_micros: 10000,
    platform_fee_micros: 296,
    total_makespan_ms: 1250,
  };

  const certificate = exportAuditCertificate(mockJob, [], [], ["rogue-node-01"]);

  assert.equal(certificate.apexmarket_version, "3.0.0-enterprise");
  assert.equal(certificate.job_id, "job-test-enterprise-42");
  assert.equal(certificate.workload_sensitivity, "CONFIDENTIAL");
  assert.equal(certificate.total_prompts, 50);
  assert.equal(certificate.quarantined_nodes.length, 1);
  assert.equal(certificate.quarantined_nodes[0], "rogue-node-01");
  assert.equal(certificate.audit_metrics.settled_cost_usd, 0.005926);
  assert.ok(certificate.audit_metrics.baseline_cost_usd > certificate.audit_metrics.settled_cost_usd);
  assert.ok(certificate.audit_metrics.net_client_savings_pct.includes("%"));
  assert.ok(certificate.cryptographic_signatures.length > 0);
  assert.equal(certificate.cryptographic_signatures[0].attestation_status, "VERIFIED_PROOF_SETTLED");
});
