"""
ApexMarket: Telemetry & Traffic Metrics Service
Tracks rolling latency, TTFT, token throughput, and error rates in Redis over a 50-request window.
"""

import json
import re
import statistics
import time
from typing import Dict, Any, List, Optional
import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas import NodeTelemetrySnapshot, NodeTrustTier

THINK_TAG_REGEX = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def strip_thinking(text_content: str) -> str:
    """
    Strips internal chain-of-thought blocks (<think>...</think>) from reasoning models
    (such as Nemotron or DeepSeek R1 derivatives) before evaluation or output presentation.
    """
    return THINK_TAG_REGEX.sub("", text_content).strip()


class TelemetryService:
    WINDOW_SIZE = 50

    @staticmethod
    def _key_ttft(node_id: str) -> str:
        return f"apex:telemetry:{node_id}:ttft"

    @staticmethod
    def _key_tps(node_id: str) -> str:
        return f"apex:telemetry:{node_id}:tps"

    @staticmethod
    def _key_errors(node_id: str) -> str:
        return f"apex:telemetry:{node_id}:errors"

    @classmethod
    async def record_request_metric(
        cls,
        redis: aioredis.Redis,
        node_id: str,
        ttft_ms: float,
        tokens_per_sec: float,
        is_error: bool,
    ) -> None:
        """
        Pushes a new latency, throughput, and error datapoint into Redis rolling lists,
        trimming strictly to the 50 most recent records.
        """
        pipe = redis.pipeline()
        k_ttft = cls._key_ttft(node_id)
        k_tps = cls._key_tps(node_id)
        k_err = cls._key_errors(node_id)

        pipe.lpush(k_ttft, str(ttft_ms))
        pipe.ltrim(k_ttft, 0, cls.WINDOW_SIZE - 1)

        pipe.lpush(k_tps, str(tokens_per_sec))
        pipe.ltrim(k_tps, 0, cls.WINDOW_SIZE - 1)

        pipe.lpush(k_err, "1" if is_error else "0")
        pipe.ltrim(k_err, 0, cls.WINDOW_SIZE - 1)

        await pipe.execute()

    @classmethod
    async def get_node_health(
        cls,
        redis: aioredis.Redis,
        node_id: str,
    ) -> Dict[str, float]:
        """
        Calculates p50, p95 TTFT, average token generation speed, and error rate
        over the rolling 50-request window from Redis.
        """
        k_ttft = cls._key_ttft(node_id)
        k_tps = cls._key_tps(node_id)
        k_err = cls._key_errors(node_id)

        pipe = redis.pipeline()
        pipe.lrange(k_ttft, 0, cls.WINDOW_SIZE - 1)
        pipe.lrange(k_tps, 0, cls.WINDOW_SIZE - 1)
        pipe.lrange(k_err, 0, cls.WINDOW_SIZE - 1)
        raw_ttfts, raw_tps, raw_errs = await pipe.execute()

        ttfts = [float(x) for x in raw_ttfts] if raw_ttfts else [100.0]
        tps = [float(x) for x in raw_tps] if raw_tps else [80.0]
        errs = [int(x) for x in raw_errs] if raw_errs else [0]

        sorted_ttfts = sorted(ttfts)
        p50_ttft = statistics.median(sorted_ttfts)
        p95_idx = min(len(sorted_ttfts) - 1, int(len(sorted_ttfts) * 0.95))
        p95_ttft = sorted_ttfts[p95_idx]

        avg_tps = statistics.mean(tps) if tps else 0.0
        error_rate = (sum(errs) / len(errs)) if errs else 0.0

        return {
            "p50_ttft_ms": round(p50_ttft, 2),
            "p95_ttft_ms": round(p95_ttft, 2),
            "tokens_per_sec": round(avg_tps, 2),
            "error_rate_50req": round(error_rate, 4),
        }

    @classmethod
    async def get_all_snapshots(
        cls,
        db: AsyncSession,
        redis: aioredis.Redis,
    ) -> List[NodeTelemetrySnapshot]:
        """
        Retrieves all active nodes from PostgreSQL and enriches each record with
        live rolling metrics from Redis.
        """
        result = await db.execute(
            text("""
                SELECT node_id, provider_name, endpoint_url, model_id, trust_tier,
                       input_price_per_1m_micros, output_price_per_1m_micros, is_active
                FROM compute_nodes
                WHERE is_active = TRUE
                ORDER BY trust_tier ASC, input_price_per_1m_micros ASC
            """)
        )
        nodes = result.fetchall()
        snapshots: List[NodeTelemetrySnapshot] = []

        for row in nodes:
            health = await cls.get_node_health(redis, row.node_id)
            snapshots.append(
                NodeTelemetrySnapshot(
                    node_id=row.node_id,
                    provider_name=row.provider_name,
                    endpoint_url=row.endpoint_url,
                    model_id=row.model_id,
                    trust_tier=NodeTrustTier(row.trust_tier),
                    input_price_per_1m_micros=row.input_price_per_1m_micros,
                    output_price_per_1m_micros=row.output_price_per_1m_micros,
                    p95_ttft_ms=health["p95_ttft_ms"],
                    tokens_per_sec=health["tokens_per_sec"],
                    error_rate_50req=health["error_rate_50req"],
                    is_active=row.is_active,
                )
            )
        return snapshots
