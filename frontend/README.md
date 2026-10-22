# ApexMarket Mission Control

Next.js 14 App Router dashboard for Engineer 4's Phase 2 assignment. Uses React Flow, Tailwind CSS, and Lucide icons. The navy/mint glass interface shows routing, batch progress, verification evidence, benchmark comparisons, and exact node balances.

## Run the dashboard

From the repository root:

```sh
cd frontend
npm ci
cp .env.example .env.local
npm run dev
```

Open http://127.0.0.1:3000. Start the Python engine separately with the root README instructions. The frontend requires Node 20 or later. `APEX_API_URL` is server-only; `NEXT_PUBLIC_WS_URL` is the browser-reachable WebSocket URL. Use `wss://` behind HTTPS.

Live mode is the default. To explicitly exercise the offline demonstration, set `NEXT_PUBLIC_MOCK_FALLBACK=true` in `.env.local` and restart Next.js. The required simulation banner stays visible at the top. Simulation never silently replaces an unavailable live connection. Change public environment values before building a production bundle.

## Operations

- **Confidential air-gap:** ON by default. Sends `CONFIDENTIAL` with new job requests. OFF sends `SYNTHETIC`; use synthetic/public templates in that mode. The control is locked during a running job so classification remains fixed.
- **Launch batch:** submit 1–5,000 prompts, cycling through newline-separated templates. Configure a spend ceiling of at most $100. Progress comes from `/ws/telemetry`; completed results are downloaded in prompt order.
- **Topology:** central router, anchor, and every registered provider. Bezier edges scale with measured throughput, using active request counts if throughput is unavailable. Green/amber/red communicate health; isolated nodes are dimmed.
- **Drift:** set `ADMIN_API_KEY`, `DEMO_CHAOS_ENABLED=true`, and a loopback-only `DEMO_MOCK_PROVIDER_URL` in the Python environment. Start `tools.mock_provider` at that URL, register it as a spot provider, and enter the admin key in Mission Control. The button configures this mock only, with redirects disabled. It cannot mutate a production provider. Live rejection messages come from persisted attestations.
- **Settle now:** configure PayPal Sandbox credentials in the Python environment and enter its `ADMIN_API_KEY` in the dashboard. Each eligible node pays whole cents from withdrawable balance, retaining the fractional remainder; probation funds are excluded. The backend rejects PayPal live mode. The browser keeps the non-secret request UUID in session storage for retries; the admin key remains in memory. A failed/ambiguous request preserves reserved funds and the same UUID. Confirmed submissions are labeled pending, then reconciled with authenticated PayPal responses. Reconciliation is also available at `POST /api/v1/ledger/payouts/{batch_id}/reconcile` with `X-Admin-Key`.

Apply `sql/schema.sql` to existing development databases before sandbox payouts; its idempotent alteration adds the payout recipient snapshot column. Destinations are frozen at reservation time so a retry has the same payload.

The server proxy forwards only explicit dashboard routes. Mutations require a same-origin request. `APEX_CLIENT_API_KEY` stays on the Next.js server; privileged actions require the supplied backend admin key.

## Benchmark provenance

`GET /api/benchmarks` reads `../benchmarks/empirical_results.csv` without caching; the dashboard refreshes every 30 seconds. Both individual runs and their mean are available for cost and makespan. The current source contains three baseline and three verified-router rows, but no execution-mode column. Its recorded costs imply 32.18% savings versus the single-provider baseline, including the harness's audit compute overhead. This is a statement about the repository CSV, not a claim that a live run was performed during frontend development.

The third comparison supports a configurable Batch API price scenario (visibly striped and labeled). Add measured `BATCH_API_BASELINE` rows with the same columns to automatically replace the scenario with recorded cost and makespan. Asynchronous delivery is labeled separately until that timing is recorded; no measured Batch API result is fabricated.

## Validation

```sh
npm test
npm run typecheck
npm run build
```

The frontend tests cover benchmark parsing, confidential isolation, simulated quarantine, exact settlement conservation, proxy allowlisting, origin checks, and credential forwarding. The Python tests include authenticated admin boundaries, sandbox-only configuration, real PostgreSQL payout reservations, ambiguous HTTP retry, destination snapshots, concurrent batches, and idempotent reconciliation. Run all backend tests with an isolated PostgreSQL test database:

```sh
TEST_DATABASE_URL=postgresql+asyncpg://USER@127.0.0.1:5432/apexmarket_test HF_HUB_OFFLINE=1 .venv/bin/pytest tests/ -q
```

The fixtures truncate that database, so use a disposable test database only.

## Three-minute narrated walkthrough

The completed [video](../docs/demo/apexmarket-mission-control.mp4), [subtitles](../docs/demo/apexmarket-mission-control.srt), and [preview](../docs/demo/preview.png) are committed under `docs/demo/`. Working captures, narration, and regenerated exports are under `output/demo/` (ignored as generated media). It uses captured states of the actual dashboard, assembled into a narrated product tour. Simulation and benchmark provenance are explained in the narration and onscreen labels.

`npm run demo:record` reassembles the tour from these nine PNG captures in `output/demo/captures/`: `01-overview`, `02-confidential`, `03-batch`, `04-routing`, `05-drift`, `06-cost`, `07-makespan`, `08-ledger`, and `09-settlement`. Capture those views again after visual changes. The assembler requires macOS `say` with Samantha plus `ffmpeg`/`ffprobe` and Python with Pillow; it uses local narration and sends no content to a voice service. Set `DEMO_PYTHON` to select the Python runtime. Set `DEMO_CAPTURE_DIR` to use another capture directory. The exported MP4 is 1280×720, H.264/AAC, with exactly 180 seconds of scene content.
