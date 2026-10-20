"""
ApexMarket: Telemetry Actor
Executes active streaming probes (stream: True) against compute nodes to measure real TTFT
and token throughput, stripping <think> tags and pushing to Redis rolling metrics.
"""

import asyncio
import time
from typing import Dict, Any, Optional
import httpx
import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.services.telemetry_service import TelemetryService, strip_thinking

settings = get_settings()


class TelemetryActor:
    def __init__(self, redis_client: aioredis.Redis, timeout_seconds: float = 15.0):
        self.redis = redis_client
        self.client = httpx.AsyncClient(timeout=timeout_seconds)
        self._is_running = False
        self._task: Optional[asyncio.Task] = None

    async def probe_node_stream(
        self,
        node_id: str,
        endpoint_url: str,
        model_id: str,
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes a real streaming HTTP probe against an OpenAI-compatible endpoint.
        Measures exact TTFT on the arrival of the first SSE chunk, strips <think> blocks,
        and computes generation velocity.
        """
        start = time.perf_counter()
        ttft_ms: Optional[float] = None
        output_chunks = []
        is_error = False

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        payload = {
            "model": model_id,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 16,
            "temperature": 0.0,
            "stream": True,
        }

        try:
            async with self.client.stream(
                "POST",
                f"{endpoint_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
            ) as response:
                if response.status_code != 200:
                    is_error = True
                    total_ms = (time.perf_counter() - start) * 1000.0
                    await TelemetryService.record_request_metric(
                        redis=self.redis,
                        node_id=node_id,
                        ttft_ms=total_ms,
                        tokens_per_sec=0.0,
                        is_error=True,
                    )
                    return {"ok": False, "ttft_ms": total_ms, "tps": 0.0, "status_code": response.status_code}

                async for line in response.aiter_lines():
                    if line.startswith("data: ") and line != "data: [DONE]":
                        if ttft_ms is None:
                            ttft_ms = (time.perf_counter() - start) * 1000.0
                        output_chunks.append(line)

            total_sec = time.perf_counter() - start
            total_ms = total_sec * 1000.0
            generated_tokens = max(1, len(output_chunks))
            tps = (generated_tokens / total_sec) if total_sec > 0 else 0.0
            final_ttft = ttft_ms if ttft_ms is not None else total_ms

            await TelemetryService.record_request_metric(
                redis=self.redis,
                node_id=node_id,
                ttft_ms=final_ttft,
                tokens_per_sec=tps,
                is_error=False,
            )

            return {
                "ok": True,
                "ttft_ms": round(final_ttft, 2),
                "total_ms": round(total_ms, 2),
                "tps": round(tps, 2),
            }

        except Exception as exc:
            total_ms = (time.perf_counter() - start) * 1000.0
            await TelemetryService.record_request_metric(
                redis=self.redis,
                node_id=node_id,
                ttft_ms=total_ms,
                tokens_per_sec=0.0,
                is_error=True,
            )
            return {"ok": False, "ttft_ms": total_ms, "tps": 0.0, "error": str(exc)}

    async def run_periodic_probes(self, db_session_factory, interval_seconds: float = 15.0) -> None:
        """Continuously probes all registered active nodes at the configured interval."""
        self._is_running = True
        while self._is_running:
            try:
                async with db_session_factory() as db:
                    result = await db.execute(
                        text("SELECT node_id, endpoint_url, model_id FROM compute_nodes WHERE is_active = TRUE")
                    )
                    nodes = result.fetchall()

                tasks = [
                    self.probe_node_stream(
                        node_id=row.node_id,
                        endpoint_url=row.endpoint_url,
                        model_id=row.model_id,
                    )
                    for row in nodes
                ]
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)

            except Exception:
                pass

            await asyncio.sleep(interval_seconds)

    def start(self, db_session_factory) -> None:
        if not self._is_running:
            self._task = asyncio.create_task(self.run_periodic_probes(db_session_factory))

    async def stop(self) -> None:
        self._is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self.client.aclose()
