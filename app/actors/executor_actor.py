"""Parallel shred executor: per-provider semaphores, per-prompt failover chain,
streaming TTFT measurement, and ordered reassembly by prompt_index.
Failover order for a prompt: assigned node -> other spot nodes (cheapest first) -> anchor.
Prompts assigned to an anchor (CONFIDENTIAL) never fail over to spot nodes.
"""
import asyncio
import json
import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import httpx

from app.config import get_settings
from app.services.progress_tracker import ProgressTracker, tracker as default_tracker


@dataclass
class ExecNode:
    node_id: str
    endpoint_url: str            # base URL incl. /v1, e.g. http://localhost:9001/v1
    model_id: str
    is_anchor: bool = False
    max_concurrent: int = 8
    input_price_per_1m_micros: int = 0
    output_price_per_1m_micros: int = 0
    api_key: Optional[str] = None

    @classmethod
    def from_candidate(cls, c, api_key: Optional[str] = None) -> "ExecNode":
        """Adapt scheduler_actor.NodeCandidate."""
        tier = getattr(c.trust_tier, "value", str(c.trust_tier))
        return cls(c.node_id, c.endpoint_url, c.model_id, tier == "ANCHOR",
                   c.max_concurrent_requests, c.input_price_per_1m_micros,
                   c.output_price_per_1m_micros, api_key)


class NodeExecutionError(RuntimeError):
    """Raised when an execution node fails."""
    pass


class UpstreamProviderError(NodeExecutionError):
    """Raised when an upstream provider fails and mock fallback is not permitted."""
    pass


class NodeCallResult(tuple):
    """4-tuple subclass preserving (text, input_tokens, output_tokens, ttft_ms) with simulation metadata."""
    def __new__(cls, text: str, in_t: int, out_t: int, ttft: float, is_simulated: bool = False, execution_mode: str = "LIVE"):
        obj = super().__new__(cls, (text, in_t, out_t, ttft))
        obj.is_simulated = is_simulated
        obj.execution_mode = execution_mode
        return obj


_shared_client: Optional[httpx.AsyncClient] = None


def get_shared_client() -> httpx.AsyncClient:
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
        )
    return _shared_client


async def close_shared_client() -> None:
    global _shared_client
    if _shared_client is not None and not _shared_client.is_closed:
        await _shared_client.aclose()
        _shared_client = None


@dataclass
class PromptResult:
    prompt_index: int
    text: str = ""
    node_id: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_micros: int = 0
    ttft_ms: float = 0.0
    failed_nodes: List[str] = field(default_factory=list)
    error: Optional[str] = None
    is_simulated: bool = False
    execution_mode: str = "LIVE" 


class ShredExecutor:
    def __init__(self, nodes: Sequence[ExecNode], client: Optional[httpx.AsyncClient] = None,
                 timeout_s: float = 30.0, breaker_threshold: int = 3,
                 tracker: Optional[ProgressTracker] = None):
        if not any(n.is_anchor for n in nodes):
            raise ValueError("Executor requires an anchor node as last-resort fallback")
        self.nodes: Dict[str, ExecNode] = {n.node_id: n for n in nodes}
        self.sems = {n.node_id: asyncio.Semaphore(max(1, n.max_concurrent)) for n in nodes}
        self._owns_client = False
        self.client = client or get_shared_client()
        self.timeout_s = timeout_s
        self.breaker_threshold = breaker_threshold
        self.fail_streak: Dict[str, int] = {n.node_id: 0 for n in nodes}
        self.tracker = tracker or default_tracker

    async def aclose(self):
        if self._owns_client and self.client is not None and not self.client.is_closed:
            await self.client.aclose()

    def _price(self, n: ExecNode) -> int:
        return n.input_price_per_1m_micros + n.output_price_per_1m_micros

    def _chain(self, assigned: str) -> List[ExecNode]:
        first = self.nodes[assigned]
        if first.is_anchor:
            return [first] + [n for n in self.nodes.values() if n.is_anchor and n is not first]
        spot = sorted((n for n in self.nodes.values() if not n.is_anchor and n is not first),
                      key=self._price)
        anchors = [n for n in self.nodes.values() if n.is_anchor]
        return [first] + spot + anchors

    def _dead(self, n: ExecNode) -> bool:
        return self.fail_streak.get(n.node_id, 0) >= self.breaker_threshold and not n.is_anchor

    async def _call_http(self, n: ExecNode, prompt: str, max_tokens: int, timeout_s: float) -> Tuple[str, int, int, float]:
        """Low-level streaming HTTP call to chat completions endpoint."""
        headers = {"Authorization": f"Bearer {n.api_key}"} if n.api_key else {}
        body = {"model": n.model_id, "max_tokens": max_tokens, "stream": True,
                "stream_options": {"include_usage": True},
                "messages": [{"role": "user", "content": prompt}]}
        url = f"{n.endpoint_url.rstrip('/')}/chat/completions"
        parts: List[str] = []
        usage = None
        ttft = 0.0
        t0 = time.perf_counter()
        async with self.client.stream("POST", url, json=body, headers=headers,
                                      timeout=timeout_s) as r:
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}")
            async for line in r.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                if chunk.get("usage"):
                    usage = chunk["usage"]
                for ch in chunk.get("choices", []):
                    piece = (ch.get("delta") or {}).get("content")
                    if piece:
                        if not parts:
                            ttft = (time.perf_counter() - t0) * 1000.0
                        parts.append(piece)
        text = "".join(parts)
        if not text:
            raise RuntimeError("empty response from node")

        from app.services.verification_service import TokenizerBillingAuthority
        in_t = (usage or {}).get("prompt_tokens") or TokenizerBillingAuthority.count_tokens(prompt)
        out_t = (usage or {}).get("completion_tokens") or TokenizerBillingAuthority.count_tokens(text)
        return NodeCallResult(text, in_t, out_t, ttft, is_simulated=False, execution_mode="LIVE")

    async def _call(self, n: ExecNode, prompt: str, max_tokens: int) -> Tuple[str, int, int, float]:
        """Legacy helper for backward compatibility."""
        return await self._call_http(n, prompt, max_tokens, self.timeout_s)

    async def _call_in_process_mock(
        self, node: ExecNode, prompt: str, max_tokens: int
    ) -> Tuple[str, int, int, float]:
        """In-process mock generation when local mock ports or external endpoints are offline."""
        import random
        from tools.mock_provider import honest_text, degraded_text
        from app.services.verification_service import TokenizerBillingAuthority
        from app.services.chaos_service import is_node_drifted

        # Simulate fast realistic TTFT (10-30ms)
        await asyncio.sleep(random.uniform(0.01, 0.03))

        is_degraded = is_node_drifted(node.node_id)
        text = degraded_text(prompt, max_tokens) if is_degraded else honest_text(prompt, max_tokens)
        in_t = TokenizerBillingAuthority.count_tokens(prompt)
        out_t = TokenizerBillingAuthority.count_tokens(text)
        ttft = random.uniform(15.0, 35.0)
        return text, in_t, out_t, ttft

    async def call_node(
        self,
        node: ExecNode,
        prompt: str,
        max_tokens: int,
        timeout_s: Optional[float] = None,
    ) -> Tuple[str, int, int, float]:
        """
        Canonical execution method for a single prompt against an ExecNode.
        Enforces:
          - Circuit breaker check: rejects immediately if circuit is open
          - Per-node concurrency semaphore
          - Active inflight tracking
          - Dynamic timeout handling
          - In-process mock fallback for localhost:8001/8002/mock-provider when offline
          - Failure streak tracking & circuit breaker status updates
          - Authoritative local token counting fallback
        Returns (text, input_tokens, output_tokens, ttft_ms).
        """
        if self._dead(node):
            raise RuntimeError(
                f"Circuit breaker OPEN for node {node.node_id} "
                f"({self.fail_streak.get(node.node_id, 0)} consecutive failures)"
            )

        sem = self.sems.setdefault(node.node_id, asyncio.Semaphore(max(1, node.max_concurrent)))
        t_out = timeout_s if timeout_s is not None else self.timeout_s

        async with sem:
            self.tracker.inflight(node.node_id, +1)
            try:
                try:
                    text, in_t, out_t, ttft = await self._call_http(node, prompt, max_tokens, timeout_s=t_out)
                    # If chaos drift is active on this node, degrade the response even if live call succeeded
                    from app.services.chaos_service import is_node_drifted
                    if is_node_drifted(node.node_id):
                        from tools.mock_provider import degraded_text
                        from app.services.verification_service import TokenizerBillingAuthority
                        text = degraded_text(prompt, max_tokens)
                        out_t = TokenizerBillingAuthority.count_tokens(text)

                    self.fail_streak[node.node_id] = 0
                    self.tracker.record(node.node_id, ttft, True)
                    return NodeCallResult(text, in_t, out_t, ttft, is_simulated=False, execution_mode="LIVE")
                except Exception as call_err:
                    is_local_mock = any(
                        node.endpoint_url.startswith(pfx)
                        for pfx in (
                            "http://localhost:8001",
                            "http://localhost:8002",
                            "http://127.0.0.1:8001",
                            "http://127.0.0.1:8002",
                            "http://mock-provider",
                        )
                    )
                    is_unconfigured_anchor = (
                        node.is_anchor
                        and (
                            node.endpoint_url.startswith("https://api.tokenfactory.nebius.com")
                            or "nebius" in node.node_id.lower()
                        )
                        and (
                            not node.api_key
                            or node.api_key in {"", "your_nebius_api_key_here"}
                            or isinstance(call_err, (httpx.ConnectError, httpx.ConnectTimeout))
                            or "401" in str(call_err)
                            or "403" in str(call_err)
                            or "502" in str(call_err)
                        )
                    )
                    if is_local_mock or is_unconfigured_anchor:
                        settings = get_settings()
                        if settings.ALLOW_MOCK_FALLBACK and settings.APP_ENV != "production":
                            text, in_t, out_t, ttft = await self._call_in_process_mock(node, prompt, max_tokens)
                            self.fail_streak[node.node_id] = 0
                            self.tracker.record(node.node_id, ttft, True)
                            return NodeCallResult(text, in_t, out_t, ttft, is_simulated=True, execution_mode="SIMULATED_MOCK")
                        raise UpstreamProviderError(
                            f"Node {node.node_id} ({node.endpoint_url}) failed: {call_err}. "
                            f"Mock fallback rejected (ALLOW_MOCK_FALLBACK={settings.ALLOW_MOCK_FALLBACK}, APP_ENV={settings.APP_ENV})."
                        ) from call_err
                    raise
            except Exception:
                self.fail_streak[node.node_id] = self.fail_streak.get(node.node_id, 0) + 1
                self.tracker.record(node.node_id, None, False)
                if self._dead(node):
                    self.tracker.set_status(node.node_id, "CIRCUIT_OPEN")
                raise
            finally:
                self.tracker.inflight(node.node_id, -1)

    async def _run_prompt(self, idx: int, prompt: str, assigned: str, max_tokens: int,
                          job_id: str) -> PromptResult:
        res = PromptResult(prompt_index=idx)
        for n in self._chain(assigned):
            if self._dead(n):
                res.failed_nodes.append(n.node_id)
                continue
            try:
                call_res = await self.call_node(n, prompt, max_tokens, timeout_s=self.timeout_s)
                text, in_t, out_t, ttft = call_res[0], call_res[1], call_res[2], call_res[3]
                is_sim = getattr(call_res, "is_simulated", False)
                mode = getattr(call_res, "execution_mode", "LIVE")
            except (httpx.HTTPError, RuntimeError, asyncio.TimeoutError, json.JSONDecodeError, NodeExecutionError) as e:
                res.failed_nodes.append(n.node_id)
                res.error = f"{n.node_id}: {e}"
                self.tracker.advance(job_id, failover=True)
                continue

            cost = math.ceil(in_t * n.input_price_per_1m_micros / 1e6
                             + out_t * n.output_price_per_1m_micros / 1e6)
            res.text, res.node_id, res.error = text, n.node_id, None
            res.input_tokens, res.output_tokens = in_t, out_t
            res.cost_micros, res.ttft_ms = cost, ttft
            res.is_simulated = is_sim
            res.execution_mode = mode
            break
        else:
            res.error = res.error or "all nodes failed"
        self.tracker.advance(job_id)
        return res

    async def run(self, job_id: str, prompts: Sequence[str],
                  assignments: Sequence[Tuple[str, Sequence[int]]],
                  max_tokens: int = 256) -> List[PromptResult]:
        """assignments: [(node_id, [prompt_index, ...]), ...]. Returns results sorted by prompt_index."""
        self.tracker.start_job(job_id, len(prompts))
        tasks = [self._run_prompt(i, prompts[i], node_id, max_tokens, job_id)
                 for node_id, idxs in assignments for i in idxs]
        results = await asyncio.gather(*tasks)
        return sorted(results, key=lambda r: r.prompt_index)
