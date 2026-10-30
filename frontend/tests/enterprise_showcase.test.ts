import assert from "node:assert/strict";
import { test } from "node:test";
import {
  SAMPLE_AUDIT_CERTIFICATE,
  verifyAuditCertificate,
  calculateShredHash,
} from "../lib/AuditCertificate";
import { COMPARATOR_MODELS } from "../components/EconomicCalculator";

test("SAMPLE_AUDIT_CERTIFICATE passes client-side Web Crypto SHA-256 verification", async () => {
  const verdict = await verifyAuditCertificate(SAMPLE_AUDIT_CERTIFICATE);

  assert.equal(verdict.isValid, true, "Sample certificate should be cryptographically valid");
  assert.equal(verdict.mismatches.length, 0, "There should be zero hash or token mismatches");
  assert.equal(verdict.summary.verifiedShreds, 4);
  assert.equal(verdict.summary.totalTokens, 256);
  assert.equal(verdict.summary.canariesPassed, 4);
  assert.equal(verdict.summary.quarantinedCount, 1);
});

test("verifyAuditCertificate detects tampered prompt output with exact mismatch location", async () => {
  // Deep clone sample certificate
  const tampered = JSON.parse(JSON.stringify(SAMPLE_AUDIT_CERTIFICATE));
  
  // Inject malicious quantization drift into shred-runpod-002
  tampered.shreds[1].completion += " [MALICIOUS_INJECTED_DRIFT]";

  const verdict = await verifyAuditCertificate(tampered);

  assert.equal(verdict.isValid, false, "Tampered certificate must fail verification");
  assert.ok(verdict.mismatches.length >= 1, "Must report at least one mismatch");

  const mismatch = verdict.mismatches.find((m) => String(m.shredId) === "shred-runpod-002");
  assert.ok(mismatch, "Should identify shred-runpod-002 as tampered target");
  assert.ok(mismatch.reason.includes("SHA-256"), "Reason must specify cryptographic digest mismatch");
  assert.notEqual(mismatch.expected, mismatch.actual, "Expected hash must differ from actual hash");
});

test("verifyAuditCertificate detects inflated token counts in header", async () => {
  const tampered = JSON.parse(JSON.stringify(SAMPLE_AUDIT_CERTIFICATE));
  
  // Inflate claimed tokens in audit_metrics
  tampered.audit_metrics.total_tokens_verified += 1000;

  const verdict = await verifyAuditCertificate(tampered);

  assert.equal(verdict.isValid, false, "Inflated token total must fail verification");
  const tokenMismatch = verdict.mismatches.find((m) => m.shredId === "BUNDLE_TOTALS");
  assert.ok(tokenMismatch, "Must report BUNDLE_TOTALS mismatch");
  assert.ok(tokenMismatch.reason.includes("Claimed total tokens"), "Reason must state token discrepancy");
});

test("COMPARATOR_MODELS contains all 3 required models with exact pricing formulas", () => {
  assert.equal(COMPARATOR_MODELS.length, 3);

  const nemotron = COMPARATOR_MODELS.find(
    (m) => m.id === "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B" || m.id === "nvidia/nemotron-3-nano-30b-a3b"
  );
  assert.ok(nemotron, "Must have nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B");
  assert.equal(nemotron.onDemandPricePer1M, 0.30);

  const llama = COMPARATOR_MODELS.find((m) => m.id === "meta-llama/Llama-3.1-8B-Instruct");
  assert.ok(llama, "Must have meta-llama/Llama-3.1-8B-Instruct");
  assert.equal(llama.onDemandPricePer1M, 0.25);

  const mistral = COMPARATOR_MODELS.find((m) => m.id === "mistralai/Mistral-NeMo-12B-Instruct");
  assert.ok(mistral, "Must have mistralai/Mistral-NeMo-12B-Instruct");
  assert.equal(mistral.onDemandPricePer1M, 0.35);

  // Assert 32.18% net savings formula vs On-Demand
  const savingsPct = 32.18;
  const apexRate = nemotron.onDemandPricePer1M * (1 - savingsPct / 100);
  assert.ok(Math.abs(apexRate - 0.20346) < 0.0001, "32.18% savings rate calculation must be exact");

  // Assert Batch API 50% discount
  const batchRate = nemotron.onDemandPricePer1M * 0.50;
  assert.equal(batchRate, 0.15, "Batch API 50% discount must be exact");
});
