# signals.py
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional
from models import Zone, MarketState
from logger import signal_logger
from config import config


@dataclass
class TradingSignal:
    zone: Zone
    signal_type: str  # 'breakout', 'rejection', 'false_breakout'
    confidence: float
    timestamp: datetime = datetime.now()

    @property
    def quality_score(self) -> float:
        return self.zone.quality_score

    def calculate_position_size(
        self, account_risk: float = config.ACCOUNT_RISK_PERCENT
    ) -> float:
        base_size = account_risk
        confidence_multiplier = self.confidence * 2
        quality_multiplier = self.quality_score / 100

        tf_multiplier = 1.0
        if any(self.zone.confirmed_tf.values()):
            tf_multiplier = 1.5

        final_size = (
            base_size * confidence_multiplier * quality_multiplier * tf_multiplier
        )
        return min(final_size, account_risk * 3)


class SignalGenerator:
    def __init__(self, min_confidence: float = config.MIN_CONFIDENCE):
        self.min_confidence = min_confidence

    def generate_signals(self, market_state: MarketState) -> List[TradingSignal]:
        signals = []

        if not market_state.active_zones:
            return signals

        current_price = (
            market_state.candles_1m[-1]["close"] if market_state.candles_1m else 0
        )

        for zone in market_state.active_zones:
            if zone.quality_score < 40:
                continue

            bounce_signal = self._check_bounce(zone, current_price, market_state)
            if bounce_signal:
                signals.append(bounce_signal)

        return signals

    def _check_bounce(
        self, zone: Zone, price: float, market_state: MarketState
    ) -> Optional[TradingSignal]:
        recent_candles = list(market_state.candles_1m)[-3:]
        if len(recent_candles) < 2:
            return None

        last_candle = recent_candles[-1]
        prev_candle = recent_candles[-2]

        if zone.zone_type.value == "support":
            touched = (
                prev_candle["low"] <= zone.zone_high
                and prev_candle["low"] >= zone.zone_low
            )
            bounced = last_candle["close"] > prev_candle["close"]

            if touched and bounced:
                confidence = self._calculate_bounce_confidence(zone, market_state)
                if confidence >= self.min_confidence:
                    return TradingSignal(zone, "rejection", confidence)

        elif zone.zone_type.value == "resistance":
            touched = (
                prev_candle["high"] >= zone.zone_low
                and prev_candle["high"] <= zone.zone_high
            )
            bounced = last_candle["close"] < prev_candle["close"]

            if touched and bounced:
                confidence = self._calculate_bounce_confidence(zone, market_state)
                if confidence >= self.min_confidence:
                    return TradingSignal(zone, "rejection", confidence)

        return None

    def _calculate_bounce_confidence(
        self, zone: Zone, market_state: MarketState
    ) -> float:
        confidence = 0.5

        if zone.volume_strength:
            confidence += zone.volume_strength * 0.2

        if zone.orderbook_strength:
            confidence += zone.orderbook_strength * 0.15

        if any(zone.confirmed_tf.values()):
            confidence += 0.15

        confidence += (zone.quality_score / 100) * 0.1

        return min(confidence, 1.0)
