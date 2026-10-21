"""Parallel shred executor: per-provider semaphores, per-prompt failover chain,
streaming TTFT measurement, and ordered reassembly by prompt_index.
Failover order for a prompt: assigned node -> other spot nodes (cheapest first) -> anchor.
Prompts assigned to an anchor (CONFIDENTIAL) never fail over to spot nodes.
"""
import asyncio, json, math, time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import httpx

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


class ShredExecutor:
    def __init__(self, nodes: Sequence[ExecNode], client: Optional[httpx.AsyncClient] = None,
                 timeout_s: float = 30.0, breaker_threshold: int = 3,
                 tracker: Optional[ProgressTracker] = None):
        if not any(n.is_anchor for n in nodes):
            raise ValueError("Executor requires an anchor node as last-resort fallback")
        self.nodes: Dict[str, ExecNode] = {n.node_id: n for n in nodes}
        self.sems = {n.node_id: asyncio.Semaphore(max(1, n.max_concurrent)) for n in nodes}
        self.client = client or httpx.AsyncClient()
        self._owns_client = client is None
        self.timeout_s = timeout_s
        self.breaker_threshold = breaker_threshold
        self.fail_streak: Dict[str, int] = {n.node_id: 0 for n in nodes}
        self.tracker = tracker or default_tracker

    async def aclose(self):
        if self._owns_client:
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
        return self.fail_streak[n.node_id] >= self.breaker_threshold and not n.is_anchor

    async def _call(self, n: ExecNode, prompt: str, max_tokens: int) -> Tuple[str, int, int, float]:
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
                                      timeout=self.timeout_s) as r:
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
                            ttft = (time.perf_counter() - t0) * 1000
                        parts.append(piece)
        text = "".join(parts)
        if not text:
            raise RuntimeError("empty response")
        in_t = (usage or {}).get("prompt_tokens") or max(1, len(prompt) // 4)
        out_t = (usage or {}).get("completion_tokens") or max(1, len(text) // 4)
        return text, in_t, out_t, ttft

    async def _run_prompt(self, idx: int, prompt: str, assigned: str, max_tokens: int,
                          job_id: str) -> PromptResult:
        res = PromptResult(prompt_index=idx)
        for n in self._chain(assigned):
            if self._dead(n):
                res.failed_nodes.append(n.node_id)
                continue
            async with self.sems[n.node_id]:
                self.tracker.inflight(n.node_id, +1)
                try:
                    text, in_t, out_t, ttft = await self._call(n, prompt, max_tokens)
                except (httpx.HTTPError, RuntimeError, asyncio.TimeoutError, json.JSONDecodeError) as e:
                    self.fail_streak[n.node_id] += 1
                    self.tracker.record(n.node_id, None, False)
                    if self._dead(n):
                        self.tracker.set_status(n.node_id, "CIRCUIT_OPEN")
                    res.failed_nodes.append(n.node_id)
                    res.error = f"{n.node_id}: {e}"
                    self.tracker.advance(job_id, failover=True)
                    continue
                finally:
                    self.tracker.inflight(n.node_id, -1)
            self.fail_streak[n.node_id] = 0
            self.tracker.record(n.node_id, ttft, True)
            cost = math.ceil(in_t * n.input_price_per_1m_micros / 1e6
                             + out_t * n.output_price_per_1m_micros / 1e6)
            res.text, res.node_id, res.error = text, n.node_id, None
            res.input_tokens, res.output_tokens = in_t, out_t
            res.cost_micros, res.ttft_ms = cost, ttft
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
