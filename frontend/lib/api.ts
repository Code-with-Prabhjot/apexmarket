import type { Job, Provider } from "./types";

export type Attestation = {
  status: string;
  node_id: string;
  canary_pass_rate: number | null;
  anchor_nll_score: number | null;
  nemotron_judge_score: number | null;
  server_hmac_attestation: string | null;
};

export type PromptResultItem = {
  prompt_index: number;
  status: string;
  executing_node_id: string;
  output_text: string;
  input_tokens: number;
  output_tokens: number;
};

export type TelemetryMetrics = {
  node_id: string;
  tokens_per_sec: number;
  p95_ttft_ms: number;
};

export type SettlementReceipt = {
  batch_id: string;
  status: string;
  total_amount_micros: number;
};

export type PayoutReceipt = {
  batch_id: string;
  status: string;
};

export type CreateJobPayload = {
  sensitivity: "CONFIDENTIAL" | "SYNTHETIC" | "PUBLIC";
  prompts: Array<{ prompt_index: number; content: string }>;
  max_tokens_per_prompt: number;
  max_cost_ceiling_micros: number;
  makespan_sla_seconds?: number;
  target_model?: string;
};

/**
 * Low-level API proxy fetcher communicating with the Next.js backend proxy.
 * Safely guards against non-JSON error pages and malformed responses.
 */
export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const cleanPath = path.replace(/^\/+/, "").replace(/\/+$/, "");
  const response = await fetch(`/api/backend/${cleanPath}`, {
    cache: "no-store",
    ...options,
  });

  const contentType = response.headers.get("content-type") || "";
  const isJson = contentType.includes("application/json");

  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    if (isJson) {
      try {
        const errorBody = await response.json();
        if (errorBody && typeof errorBody.detail === "string") {
          detail = errorBody.detail;
        } else if (errorBody && typeof errorBody.message === "string") {
          detail = errorBody.message;
        }
      } catch (err) {
        console.warn(`[ApexMarket API] Could not parse error JSON from /api/backend/${cleanPath}:`, err);
      }
    } else {
      const errorText = await response.text();
      console.warn(
        `[ApexMarket API] Non-JSON error (${response.status}) from /api/backend/${cleanPath}:`,
        errorText.slice(0, 160)
      );
    }
    throw new Error(detail);
  }

  if (!isJson) {
    const raw = await response.text();
    console.warn(
      `[ApexMarket API] Expected JSON from /api/backend/${cleanPath} but received ${contentType || "none"}:`,
      raw.slice(0, 160)
    );
    throw new Error(`Unexpected non-JSON response from server (${response.status})`);
  }

  try {
    return (await response.json()) as T;
  } catch (err) {
    console.warn(`[ApexMarket API] JSON.parse error for /api/backend/${cleanPath}:`, err);
    throw new Error(`Invalid JSON response from server (${response.status})`);
  }
}

/**
 * Submits a new batch inference job to the backend.
 * POST /api/v1/jobs
 */
export async function createJob(payload: CreateJobPayload): Promise<Job> {
  return api<Job>("jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

/**
 * Retrieves the status and accounting metadata for a given batch job.
 * GET /api/v1/jobs/{job_id}
 */
export async function getJob(jobId: string): Promise<Job> {
  return api<Job>(`jobs/${jobId}`);
}

/**
 * Retrieves reassembled prompt output items for a completed or partial job.
 * GET /api/v1/jobs/{job_id}/results
 */
export async function getJobResults(jobId: string): Promise<PromptResultItem[]> {
  return api<PromptResultItem[]>(`jobs/${jobId}/results`);
}

/**
 * Retrieves cryptographic verification attestations for a given job.
 * GET /api/v1/jobs/{job_id}/attestations
 */
export async function getJobAttestations(jobId: string): Promise<Attestation[]> {
  return api<Attestation[]>(`jobs/${jobId}/attestations`);
}

/**
 * Retrieves list of registered compute nodes.
 * GET /api/v1/nodes
 */
export async function getNodes(): Promise<Provider[]> {
  return api<Provider[]>("nodes");
}

/**
 * Retrieves rolling telemetry and throughput metrics.
 * GET /api/v1/telemetry
 */
export async function getTelemetry(): Promise<TelemetryMetrics[]> {
  return api<TelemetryMetrics[]>("telemetry");
}

/**
 * Triggers PayPal Sandbox settlement for accumulated withdrawable balances.
 * POST /api/v1/ledger/settle-now
 */
export async function settleNow(
  adminKey: string,
  idempotencyKey?: string
): Promise<SettlementReceipt> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "X-Admin-Key": adminKey,
  };
  if (idempotencyKey) {
    headers["Idempotency-Key"] = idempotencyKey;
  }
  return api<SettlementReceipt>("ledger/settle-now", {
    method: "POST",
    headers,
    body: "{}",
  });
}

/**
 * Reconciles a pending PayPal Sandbox payout batch status.
 * POST /api/v1/ledger/payouts/{batch_id}/reconcile
 */
export async function reconcilePayout(
  batchId: string,
  adminKey: string
): Promise<PayoutReceipt> {
  return api<PayoutReceipt>(`ledger/payouts/${batchId}/reconcile`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Admin-Key": adminKey,
    },
    body: "{}",
  });
}

/**
 * Injects degradation/drift chaos into the local mock provider.
 * POST /api/v1/demo/drift
 */
export async function setDemoDrift(
  degraded: boolean,
  adminKey: string
): Promise<void> {
  await api<void>("demo/drift", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Admin-Key": adminKey,
    },
    body: JSON.stringify({ degraded }),
  });
}

/**
 * Resolves the WebSocket URL for live telemetry streaming.
 */
export function getWebSocketTelemetryUrl(): string {
  if (typeof window === "undefined") {
    return process.env.NEXT_PUBLIC_WS_URL || "ws://127.0.0.1:8000/ws/telemetry";
  }
  return (
    process.env.NEXT_PUBLIC_WS_URL ||
    `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.hostname}:8000/ws/telemetry`
  );
}
