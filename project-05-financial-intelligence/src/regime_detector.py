"""
regime_detector.py
~~~~~~~~~~~~~~~~~~
Classifies the current market regime using VIX, yield curve, and momentum signals.
Regime biases which agents the SelectorGroupChat prioritizes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

import yfinance as yf

logger = logging.getLogger(__name__)


class MarketRegime(str, Enum):
    RISK_ON = "risk_on"
    RISK_OFF = "risk_off"
    TRENDING = "trending"
    RANGE_BOUND = "range_bound"


@dataclass
class RegimeAnalysis:
    regime: MarketRegime
    confidence: float
    signals: dict[str, Any]
    agent_priority: list[str]
    context_prompt: str


async def detect_regime() -> RegimeAnalysis:
    """
    Detect current market regime using live market data.
    Returns regime classification with agent priority hints.
    """
    signals = {}

    try:
        # VIX (fear gauge)
        vix = yf.Ticker("^VIX")
        vix_data = vix.history(period="5d")
        signals["vix"] = float(vix_data["Close"].iloc[-1]) if not vix_data.empty else 20.0

        # S&P 500 momentum (20d vs 50d SMA)
        spy = yf.Ticker("SPY")
        spy_data = spy.history(period="60d")
        if len(spy_data) >= 50:
            sma20 = spy_data["Close"].tail(20).mean()
            sma50 = spy_data["Close"].tail(50).mean()
            signals["spy_momentum"] = (sma20 / sma50 - 1) * 100
        else:
            signals["spy_momentum"] = 0.0

        # 10Y-2Y yield curve spread (credit stress proxy)
        tnx = yf.Ticker("^TNX")  # 10Y yield
        irx = yf.Ticker("^IRX")  # 13-week yield (proxy for 2Y)
        tnx_data = tnx.history(period="5d")
        irx_data = irx.history(period="5d")
        if not tnx_data.empty and not irx_data.empty:
            signals["yield_spread"] = float(tnx_data["Close"].iloc[-1] - irx_data["Close"].iloc[-1])
        else:
            signals["yield_spread"] = 0.5

    except Exception as e:
        logger.warning("Could not fetch live market data: %s. Using neutral defaults.", e)
        signals = {"vix": 20.0, "spy_momentum": 0.0, "yield_spread": 0.5}

    # Classify regime
    vix = signals["vix"]
    momentum = signals["spy_momentum"]
    spread = signals["yield_spread"]

    if vix > 25 or spread < -0.5:
        regime = MarketRegime.RISK_OFF
        confidence = min(0.9, (vix - 25) / 15 + 0.6) if vix > 25 else 0.7
        agent_priority = ["RiskAgent", "MacroAgent", "EarningsAgent", "SentimentAgent", "SynthesisAgent"]
        context = f"Market is in RISK-OFF regime (VIX={vix:.1f}, spread={spread:.2f}). Focus on risk management and macro factors."

    elif vix < 15 and momentum > 1.0:
        regime = MarketRegime.RISK_ON
        confidence = 0.75
        agent_priority = ["EarningsAgent", "SentimentAgent", "RiskAgent", "MacroAgent", "SynthesisAgent"]
        context = f"Market is in RISK-ON regime (VIX={vix:.1f}, SPY momentum={momentum:.1f}%). Focus on earnings quality and sentiment."

    elif abs(momentum) > 2.0:
        regime = MarketRegime.TRENDING
        confidence = min(0.85, abs(momentum) / 5)
        agent_priority = ["SentimentAgent", "RiskAgent", "EarningsAgent", "MacroAgent", "SynthesisAgent"]
        context = f"Market is TRENDING (momentum={momentum:.1f}%). Focus on sentiment and momentum risk."

    else:
        regime = MarketRegime.RANGE_BOUND
        confidence = 0.60
        agent_priority = ["MacroAgent", "EarningsAgent", "SentimentAgent", "RiskAgent", "SynthesisAgent"]
        context = f"Market is RANGE-BOUND (VIX={vix:.1f}, momentum={momentum:.1f}%). Focus on fundamental analysis."

    return RegimeAnalysis(
        regime=regime,
        confidence=confidence,
        signals=signals,
        agent_priority=agent_priority,
        context_prompt=context,
    )
