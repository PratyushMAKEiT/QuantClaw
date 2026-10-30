# ==============================================================================
# quantclaw/ai_engine.py — Claude AI Co-Pilot & 24/7 Market Discussion Engine
# ==============================================================================
"""
Claude AI Co-Pilot & 24/7 Market Intelligence Layer for QuantClaw MT5.
Supports Claude Sonnet 4.6 / 3.7 / 3.5.

Capabilities:
  1. Strategic Trade Setup Validation (Optional deep reasoning co-pilot)
  2. 24/7 AI Market Discussion & Tactical Briefings
  3. Continuous Self-Tuning & Parameter Optimization Reports (antigravity_tuning_report.md)
  4. 100% Autonomous Fallback: Operates flawlessly using local ML Brain if offline or no key provided.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, Dict, List, Optional
import anthropic

from quantclaw.utils.logger import get_logger
from quantclaw.models import StrategySignal, RiskRegime
from quantclaw.config import save_json_persisted, load_json_persisted

logger = get_logger("ai_engine")

PROMPT_EVALUATION = """You are a Senior Quantitative Trading AI Co-Pilot for MetaTrader 5.
Analyze this technical setup for {symbol} ({action}) and provide validation.

Market Context:
{market_context}

Signal Details:
- Strategy: {strategy}
- Price: {price}
- Timeframe: {timeframe}
- Strength: {strength}
- ML Brain Confluence: {ml_score}/100

Guidelines:
- Confirm trend structure, liquidity pools, and momentum.
- Classify regime into ALPHA (tight scalp), BETA (standard 1:1.5), or GAMMA (high conviction runner).
- Return ONLY valid JSON:
{{"approved": true/false, "confidence": 0-100, "regime": "ALPHA"|"BETA"|"GAMMA", "commentary": "under 20 words rationale"}}
"""


class AIEngine:
    """Claude AI Co-Pilot & Market Discussion Engine."""

    def __init__(self, api_key: str = "", model: str = "claude-3-5-sonnet-20241022", timeout_sec: float = 10.0) -> None:
        self.api_key = api_key.strip() if api_key else ""
        # Normalize legacy/invalid model names to a valid production model
        self.model = self._normalize_model(model)
        self.timeout_sec = timeout_sec

        self._client: Optional[anthropic.AsyncAnthropic] = None
        self._init_client()
        self._discussions: List[Dict[str, Any]] = []

    @staticmethod
    def _normalize_model(model: str) -> str:
        """Ensure model is a valid Anthropic production model ID."""
        valid_models = {
            "claude-3-5-sonnet-20241022", "claude-3-7-sonnet-20250219",
            "claude-3-opus-20240229", "claude-3-haiku-20240307",
            "claude-3-5-haiku-20241022", "claude-sonnet-4-6", "claude-opus-4-5"
        }
        if model in valid_models:
            return model
        # Remap known aliases / legacy IDs
        if "sonnet" in model.lower():
            return "claude-3-5-sonnet-20241022"
        if "opus" in model.lower():
            return "claude-3-opus-20240229"
        if "haiku" in model.lower():
            return "claude-3-5-haiku-20241022"
        return "claude-3-5-sonnet-20241022"  # Safe default

    def _init_client(self) -> None:
        if self.api_key:
            try:
                self._client = anthropic.AsyncAnthropic(api_key=self.api_key, timeout=self.timeout_sec)
            except Exception as e:
                logger.debug(f"Failed to initialize Anthropic client: {e}")
                self._client = None
        else:
            self._client = None

    def update_api_key(self, api_key: str) -> None:
        """Update API key at runtime."""
        self.api_key = api_key.strip() if api_key else ""
        self._init_client()
        logger.info(f"AI Engine API key updated (Available: {self.is_available()})")

    def is_available(self) -> bool:
        """Check if Claude API client is active and configured."""
        return self._client is not None and bool(self.api_key)

    @staticmethod
    def _extract_json(raw_text: str) -> Optional[Dict[str, Any]]:
        """
        Robustly extract a JSON object from raw LLM text.
        Handles markdown fences, leading/trailing text, and multiple braces.
        """
        import re
        # Strip markdown code fences if present
        raw_text = re.sub(r"```(?:json)?", "", raw_text).strip()
        # Try to find outermost {...}
        matches = list(re.finditer(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)?\}", raw_text, re.DOTALL))
        for m in reversed(matches):  # Prefer last/largest JSON object
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                continue
        # Last resort: find first { and last }
        start = raw_text.find("{")
        end = raw_text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(raw_text[start:end + 1])
            except json.JSONDecodeError:
                pass
        return None

    @staticmethod
    def _validate_ai_response(data: Dict[str, Any], ml_score: float) -> Dict[str, Any]:
        """Validate and fill missing required fields in Claude's response."""
        return {
            "approved": bool(data.get("approved", ml_score >= 65.0)),
            "confidence": int(data.get("confidence", int(ml_score))),
            "regime": str(data.get("regime", "BETA")),
            "commentary": str(data.get("commentary", data.get("comment", "AI validated"))),
        }

    # ── Trade Validation ───────────────────────────────────────────────────────

    async def validate_trade(
        self, signal: StrategySignal, market_context: Dict[str, Any], ml_score: float
    ) -> Dict[str, Any]:
        """
        Validate trade setup via Claude.
        If offline, falls back seamlessly to ML Brain verdict.
        """
        if not self.is_available():
            # Offline mode: Pass through based on ML Brain
            return {
                "approved": ml_score >= 65.0,
                "confidence": int(ml_score),
                "regime": "GAMMA" if ml_score >= 80 else ("BETA" if ml_score >= 68 else "ALPHA"),
                "commentary": "Validated by local ML Brain (offline mode)",
            }

        try:
            prompt = PROMPT_EVALUATION.format(
                symbol=signal.symbol,
                action=signal.action.upper(),
                market_context=json.dumps(market_context, indent=2),
                strategy=signal.strategy,
                price=signal.price,
                timeframe=signal.timeframe,
                strength=signal.strength,
                ml_score=ml_score,
            )

            resp = await self._client.messages.create(
                model=self.model,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )

            raw_text = resp.content[0].text.strip()
            data = self._extract_json(raw_text)
            if data:
                validated = self._validate_ai_response(data, ml_score)
                logger.info(f"🤖 Claude AI Validation: {signal.symbol} -> {validated.get('commentary', '')}")
                approved = validated.get('approved', False)
                confidence = validated.get('confidence', 0)
                commentary = f"[AI-{signal.strategy}] {signal.symbol} {signal.action.upper()}: {'APPROVED' if approved else 'REJECTED'} (conf={confidence:.0f}) — {validated.get('commentary', '')[:100]}"
                if hasattr(self, '_discussions'):
                    self._discussions.append({"ts": time.time(), "symbol": signal.symbol, "text": commentary})
                    self._discussions = self._discussions[-100:]  # Keep last 100
                return validated
        except Exception as e:
            logger.debug(f"Claude validation exception: {e}")

        # Safe fallback
        return {
            "approved": ml_score >= 65.0,
            "confidence": int(ml_score),
            "regime": "BETA",
            "commentary": "Fallback to local ML Brain evaluation",
        }


    # ── 24/7 AI Market Discussion ──────────────────────────────────────────────

    async def generate_market_discussion(self, symbol: str, analysis: Dict[str, Any]) -> str:
        """Generate 24/7 tactical market commentary for symbol."""
        if not self.is_available():
            trend = analysis.get("trend", "NEUTRAL")
            price = analysis.get("price", 0.0)
            rsi = analysis.get("rsi", 50.0)
            return f"[{symbol}] {trend} bias at ${price:.4f}. RSI: {rsi:.1f}. Multi-strategy scanning active."

        try:
            prompt = (
                f"Give a concise 2-sentence tactical briefing for {symbol} based on this data:\n"
                f"{json.dumps(analysis, indent=2)}\n"
                f"Highlight key levels, SMC liquidity zones, and active bias."
            )
            resp = await self._client.messages.create(
                model=self.model,
                max_tokens=150,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text.strip()
            self._discussions.append({
                "symbol": symbol,
                "text": text,
                "time": time.time(),
            })
            if len(self._discussions) > 50:
                self._discussions.pop(0)
            return text
        except Exception as e:
            logger.debug(f"AI discussion error: {e}")
            return f"[{symbol}] Autonomous 24/7 market monitoring active."

    def get_recent_discussions(self) -> List[Dict[str, Any]]:
        """Return cached recent AI market discussions."""
        return list(reversed(self._discussions))
