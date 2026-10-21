"""Fully in-process (mock provider via MockTransport+ASGITransport). No Docker/DB/Redis/API key."""
import httpx, pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.actors.executor_actor import ExecNode, ShredExecutor
from app.api.routes_ws import router as ws_router
from app.services.progress_tracker import ProgressTracker
from tools.mock_provider import create_app, honest_text


def mk(name, **over):
    cfg = {"name": name, "ttft_ms": 1, "token_delay_ms": 0, "fail_rate": 0.0,
           "fail_status": 503, "degraded": False}
    cfg.update(over)
    return create_app(cfg)


def client_for(apps: dict) -> httpx.AsyncClient:
    async def handler(request: httpx.Request) -> httpx.Response:
        t = httpx.ASGITransport(app=apps[request.url.host])
        return await t.handle_async_request(request)
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def nodes():
    return [
        ExecNode("anchor", "http://anchor/v1", "m", is_anchor=True, max_concurrent=4,
                 input_price_per_1m_micros=100_000, output_price_per_1m_micros=400_000),
        ExecNode("spot1", "http://spot1/v1", "m", max_concurrent=4,
                 input_price_per_1m_micros=40_000, output_price_per_1m_micros=160_000),
        ExecNode("spot2", "http://spot2/v1", "m", max_concurrent=4,
                 input_price_per_1m_micros=60_000, output_price_per_1m_micros=240_000),
    ]


PROMPTS = [f"prompt number {i}" for i in range(12)]


@pytest.mark.asyncio
async def test_ordered_reassembly_across_nodes():
    apps = {n: mk(n) for n in ("anchor", "spot1", "spot2")}
    ex = ShredExecutor(nodes(), client_for(apps), tracker=ProgressTracker())
    assign = [("spot2", [11, 3, 7]), ("spot1", [0, 5, 9, 1]), ("anchor", [2, 4, 6, 8, 10])]
    res = await ex.run("j1", PROMPTS, assign, max_tokens=5)
    assert [r.prompt_index for r in res] == list(range(12))
    assert all(r.text == honest_text(PROMPTS[r.prompt_index], 5) for r in res)
    assert all(r.cost_micros > 0 for r in res)


@pytest.mark.asyncio
async def test_failover_spot_to_next_cheapest_then_anchor():
    apps = {"anchor": mk("anchor"), "spot1": mk("spot1", fail_rate=1.0), "spot2": mk("spot2")}
    ex = ShredExecutor(nodes(), client_for(apps), tracker=ProgressTracker())
    res = await ex.run("j2", PROMPTS, [("spot1", list(range(12)))], max_tokens=5)
    assert all(r.error is None and r.node_id == "spot2" for r in res)
    assert any("spot1" in r.failed_nodes for r in res)

    apps["spot2"].state.cfg["fail_rate"] = 1.0
    ex2 = ShredExecutor(nodes(), client_for(apps), tracker=ProgressTracker())
    res = await ex2.run("j3", PROMPTS, [("spot1", list(range(12)))], max_tokens=5)
    assert all(r.node_id == "anchor" and r.error is None for r in res)


@pytest.mark.asyncio
async def test_circuit_breaker_stops_hammering_dead_node():
    apps = {"anchor": mk("anchor"), "spot1": mk("spot1", fail_rate=1.0), "spot2": mk("spot2")}
    tr = ProgressTracker()
    ex = ShredExecutor(nodes(), client_for(apps), breaker_threshold=3, tracker=tr)
    res = await ex.run("j4", PROMPTS, [("spot1", list(range(12)))], max_tokens=5)
    assert all(r.error is None for r in res)
    assert tr.nodes["spot1"]["status"] == "CIRCUIT_OPEN"


@pytest.mark.asyncio
async def test_confidential_anchor_never_fails_over_to_spot():
    apps = {"anchor": mk("anchor", fail_rate=1.0), "spot1": mk("spot1"), "spot2": mk("spot2")}
    tr = ProgressTracker()
    ex = ShredExecutor(nodes(), client_for(apps), tracker=tr)
    res = await ex.run("j5", PROMPTS[:3], [("anchor", [0, 1, 2])], max_tokens=5)
    assert all(r.error and r.node_id is None for r in res)
    assert "spot1" not in tr.nodes and "spot2" not in tr.nodes


@pytest.mark.asyncio
async def test_semaphore_caps_concurrency():
    apps = {n: mk(n, ttft_ms=20) for n in ("anchor", "spot1", "spot2")}
    ns = nodes()
    ns[1].max_concurrent = 2
    tr = ProgressTracker()
    peak = {"v": 0}
    orig = tr.inflight

    def spy(nid, d):
        orig(nid, d)
        if nid == "spot1":
            peak["v"] = max(peak["v"], tr.nodes["spot1"]["active"])
    tr.inflight = spy
    ex = ShredExecutor(ns, client_for(apps), tracker=tr)
    await ex.run("j6", PROMPTS, [("spot1", list(range(12)))], max_tokens=5)
    assert 0 < peak["v"] <= 2


def test_ws_telemetry_streams_snapshots():
    from app.services.progress_tracker import tracker
    tracker.record("spot1", 42.0, True)
    a = FastAPI()
    a.include_router(ws_router)
    with TestClient(a).websocket_connect("/ws/telemetry?max_msgs=3") as ws:
        msgs = [ws.receive_json() for _ in range(3)]
    assert any(n["node_id"] == "spot1" for n in msgs[0]["nodes"])
    assert msgs[2]["ts"] > msgs[0]["ts"]
