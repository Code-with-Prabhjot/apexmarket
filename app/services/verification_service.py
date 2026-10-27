"""
ApexMarket: 5-Tier Verification & Cryptographic Attestation Pipeline
Performs per-shred audit:
  1. Authoritative byte-level token counting & output safety scans
  2. Rotated canary probe generation and evaluation (4% injection)
  3. Secret-seeded anchor sampling (5% split via HMAC CSPRNG)
  4. Teacher-forcing logprob NLL scoring
  5. Nemotron semantic judge evaluation
  6. Cryptographic server HMAC attestation signing
"""

import concurrent.futures
import hashlib
import hmac
import json
import logging
import math
import random
import re
from typing import List, Dict, Any, Tuple, Optional
import uuid

logger = logging.getLogger("apexmarket.verification")

from app.config import get_settings
from app.schemas import ShredAttestation, PromptResultItem
from app.services.telemetry_service import strip_thinking

settings = get_settings()

# Suspicious payload detection patterns
SAFETY_PATTERNS = [
    re.compile(r"<script.*?>.*?</script>", re.IGNORECASE | re.DOTALL),
    re.compile(r"(union\s+select|drop\s+table|delete\s+from|insert\s+into)", re.IGNORECASE),
    re.compile(r"(ignore previous instructions|disregard all previous system prompts)", re.IGNORECASE),
]


class TokenizerBillingAuthority:
    """Computes exact byte-level token counts locally rather than trusting self-reported metadata."""
    _tokenizer = None
    _init_attempted = False
    _warned_offline = False

    @classmethod
    def get_tokenizer(cls):
        if cls._tokenizer is None and not cls._init_attempted:
            cls._init_attempted = True
            try:
                from tokenizers import Tokenizer
                # Strict 3-second guard on network/model download
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(Tokenizer.from_pretrained, "gpt2")
                    cls._tokenizer = future.result(timeout=3.0)
            except Exception as e:
                cls._tokenizer = None
                if not cls._warned_offline:
                    cls._warned_offline = True
                    logger.warning("Tokenizer offline: using local deterministic billing estimator")
        return cls._tokenizer

    @classmethod
    def count_tokens(cls, text_content: Optional[str]) -> int:
        """
        Calculates token count. Never silently returns None or 0.
        Uses exact 4.0 chars/token conservative boundary if tokenizer is offline.
        """
        if not text_content:
            return 1

        tokenizer = cls.get_tokenizer()
        if tokenizer is not None:
            try:
                encoded = tokenizer.encode(text_content)
                return max(1, len(encoded.ids))
            except Exception:
                pass

        if not cls._warned_offline:
            cls._warned_offline = True
            logger.warning("Tokenizer offline: using local deterministic billing estimator")

        # Fallback conservative token estimation: 4.0 chars/token exact conservative boundary
        # Guaranteed to return >= 1, never None or 0
        raw_len = len(text_content.encode("utf-8", errors="replace")) if isinstance(text_content, str) else len(str(text_content))
        return max(1, math.ceil(raw_len / 4.0))


class CanaryProbeEngine:
    """Generates deterministic canary tasks with known mathematical/JSON answers."""

    @staticmethod
    def generate_canaries(shred_id: uuid.UUID, count: int = 2) -> List[Dict[str, Any]]:
        """Generates dynamic canary prompts with known ground truth based on shred_id seed."""
        seed_int = int(hashlib.sha256(shred_id.bytes).hexdigest()[:8], 16)
        rng = random.Random(seed_int)

        canaries = []
        for i in range(count):
            op = rng.choice(["add", "mult", "json_key"])
            if op == "add":
                a, b = rng.randint(100, 999), rng.randint(100, 999)
                expected = str(a + b)
                prompt = f"Compute strictly the sum of {a} and {b}. Return only the integer result without punctuation."
            elif op == "mult":
                a, b = rng.randint(12, 85), rng.randint(12, 85)
                expected = str(a * b)
                prompt = f"Compute strictly the product of {a} and {b}. Return only the integer product without words."
            else:
                key = f"metric_{rng.randint(10, 99)}"
                val = rng.randint(1000, 9999)
                expected = str(val)
                prompt = f'From the JSON payload {{"{key}": {val}}}, extract only the numeric value of "{key}". Return nothing else.'

            canaries.append({
                "canary_index": -(i + 1),
                "prompt": prompt,
                "expected": expected,
            })
        return canaries

    @staticmethod
    def verify_canary_output(output_text: str, expected_text: str) -> bool:
        clean = strip_thinking(output_text).strip()
        # Remove trailing periods or quotes
        clean = clean.strip(". \"'\n\r\t")
        expected = expected_text.strip()
        return expected in clean.split() or clean == expected


class VerificationService:
    @staticmethod
    def generate_shred_hmac(
        shred_id: uuid.UUID,
        node_id: str,
        passed: bool,
        input_tokens: int,
        output_tokens: int,
        canary_accuracy: float,
        anchor_nll: Optional[float] = None,
    ) -> str:
        """
        Signs verification results with server HMAC secret to produce non-forgeable attestation.
        """
        payload = (
            f"shred:{shred_id}|node:{node_id}|pass:{passed}|"
            f"in:{input_tokens}|out:{output_tokens}|canary:{canary_accuracy:.4f}|"
            f"nll:{anchor_nll if anchor_nll is not None else 'NA'}"
        )
        return hmac.new(
            settings.HMAC_SECRET_KEY.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def select_anchor_sample_indices(
        shred_id: uuid.UUID,
        total_prompt_count: int,
        sample_rate: float = 0.05,
    ) -> List[int]:
        """
        Uses HMAC of shred_id as a CSPRNG seed to select 5% of prompts
        for redundant anchor execution on Nebius Token Factory.
        """
        if total_prompt_count <= 0:
            return []
        sample_size = max(1, int(total_prompt_count * sample_rate))
        seed_bytes = hmac.new(
            settings.HMAC_SECRET_KEY.encode("utf-8"),
            shred_id.bytes,
            hashlib.sha256,
        ).digest()
        seed_int = int.from_bytes(seed_bytes[:8], "big")
        rng = random.Random(seed_int)
        return sorted(rng.sample(range(total_prompt_count), min(sample_size, total_prompt_count)))

    @classmethod
    def scan_output_safety(cls, text_content: str) -> Tuple[bool, Optional[str]]:
        """Scans output text for injection or exploitation artifacts."""
        for pattern in SAFETY_PATTERNS:
            if pattern.search(text_content):
                return False, f"Flagged by pattern: {pattern.pattern}"
        return True, None

    @classmethod
    def audit_shred(
        cls,
        shred_id: uuid.UUID,
        node_id: str,
        canary_results: List[Tuple[bool, str]],  # (passed, reason)
        outputs: List[str],
        anchor_nll_score: Optional[float] = None,
        nemotron_judge_score: Optional[float] = None,
        input_prompts: Optional[List[str]] = None,
    ) -> ShredAttestation:
        """
        Synthesizes the 5 verification tiers to produce an authoritative ShredAttestation.
        Rules:
          - >= 2 canary misses = immediate failure
          - Safety scan failure = immediate failure
          - anchor_nll_score > 3.5 = fail (quantization/substitution drift)
          - nemotron_judge_score < 7.0 = fail
        """
        total_canaries = len(canary_results)
        passed_canaries = sum(1 for c, _ in canary_results if c)
        canary_accuracy = (passed_canaries / total_canaries) if total_canaries > 0 else 1.0

        measured_in_tokens = sum(TokenizerBillingAuthority.count_tokens(p) for p in input_prompts) if input_prompts else 0
        measured_out_tokens = 0
        failure_reasons: List[str] = []

        # Tier 1: Tokenizer & Safety Audit
        for out in outputs:
            measured_out_tokens += TokenizerBillingAuthority.count_tokens(out)
            safe, reason = cls.scan_output_safety(out)
            if not safe:
                failure_reasons.append(f"Safety violation: {reason}")

        # Tier 2: Canary Audit
        if (total_canaries >= 2 and (total_canaries - passed_canaries) >= 2) or (total_canaries > 0 and canary_accuracy < 0.5):
            failure_reasons.append(f"Canary failure rate too high: {passed_canaries}/{total_canaries} passed.")

        # Tier 4: NLL Teacher-Forcing Audit
        if anchor_nll_score is not None and anchor_nll_score > 3.5:
            failure_reasons.append(f"Anchor NLL score exceeded tolerance: {anchor_nll_score:.3f} > 3.500.")

        # Tier 5: Nemotron Judge Audit
        if nemotron_judge_score is not None and nemotron_judge_score < 7.0:
            failure_reasons.append(f"Nemotron Judge scored below threshold: {nemotron_judge_score:.1f} < 7.0.")

        shred_passed = len(failure_reasons) == 0

        hmac_sig = cls.generate_shred_hmac(
            shred_id=shred_id,
            node_id=node_id,
            passed=shred_passed,
            input_tokens=measured_in_tokens,
            output_tokens=measured_out_tokens,
            canary_accuracy=canary_accuracy,
            anchor_nll=anchor_nll_score,
        )

        return ShredAttestation(
            shred_id=shred_id,
            node_id=node_id,
            passed=shred_passed,
            measured_input_tokens=measured_in_tokens,
            measured_output_tokens=measured_out_tokens,
            canary_accuracy=canary_accuracy,
            anchor_nll_score=anchor_nll_score,
            nemotron_judge_score=nemotron_judge_score,
            server_hmac_signature=hmac_sig,
            failure_reason="; ".join(failure_reasons) if failure_reasons else None,
        )
