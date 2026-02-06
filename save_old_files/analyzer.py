# analyzer.py
import asyncio
import json
import redis
from datetime import datetime
from typing import Dict, List
from models import MarketState
from detectors import ZoneDetector
from confirmations import ConfirmationSystem
from signals import SignalGenerator, TradingSignal
from logger import app_logger, signal_logger, perf_logger
from config import config
from models import Zone


class AdvancedZoneAnalyzer:
    def __init__(self):
        self.market_state = MarketState()
        self.zone_detector = ZoneDetector()
        self.confirmation_system = ConfirmationSystem()
        self.signal_generator = SignalGenerator()
        self.last_analysis_time = datetime.now()

    async def process_message(self, topic: str, data: Dict):
        start_time = datetime.now()

        try:
            if "kline" in topic:
                await self._process_candle(topic, data)
            elif "orderbook" in topic:
                await self._process_orderbook(data)
            elif "publicTrade" in topic:
                await self._process_trades(data)

            if (
                datetime.now() - self.last_analysis_time
            ).total_seconds() >= config.ANALYSIS_INTERVAL_SECONDS:
                await self._run_analysis()
                self.last_analysis_time = datetime.now()

        except Exception as e:
            app_logger.error(f"Error processing message: {e}")

        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        perf_logger.debug(f"Processing time: {processing_time:.1f}ms")

    async def _process_candle(self, topic: str, data: Dict):
        kline_data = data.get("data", [])
        if not kline_data:
            return

        k = kline_data[0]
        candle = {
            "open": float(k["open"]),
            "high": float(k["high"]),
            "low": float(k["low"]),
            "close": float(k["close"]),
            "volume": float(k["volume"]),
        }

        if "kline.1." in topic:
            self.market_state.add_candle(candle, "1m")
        elif "kline.5." in topic:
            self.market_state.add_candle(candle, "5m")
        elif "kline.60." in topic:
            self.market_state.add_candle(candle, "1h")

    async def _process_orderbook(self, data: Dict):
        orderbook_data = data.get("data", {})
        if orderbook_data:
            self.market_state.orderbook = {
                "bids": orderbook_data.get("b", []),
                "asks": orderbook_data.get("a", []),
            }

    async def _process_trades(self, data: Dict):
        trades_data = data.get("data", [])
        for trade in trades_data:
            self.market_state.recent_trades.append(
                {
                    "price": float(trade["p"]),
                    "qty": float(trade["v"]),
                    "side": trade.get("S", "unknown"),
                    "timestamp": datetime.now(),
                }
            )

    async def _run_analysis(self):
        zones = self.zone_detector.detect_zones(self.market_state)

        for zone in zones:
            if self.market_state.orderbook:
                self.confirmation_system.confirm_with_orderbook(
                    zone, self.market_state.orderbook
                )

            if self.market_state.candles_1m:
                self.confirmation_system.confirm_with_volume(
                    zone, list(self.market_state.candles_1m)[-100:]
                )

            self.confirmation_system.confirm_multiple_timeframes(
                zone, self.market_state
            )

        self.market_state.active_zones = zones
        signals = self.signal_generator.generate_signals(self.market_state)

        for signal in signals:
            await self._handle_signal(signal)

        self._log_analysis_results(zones, signals)

    async def _handle_signal(self, signal: TradingSignal):
        position_size = signal.calculate_position_size()

        signal_logger.info(
            f"📈 {signal.signal_type.upper()} | "
            f"Zone: {signal.zone.zone_type.value} {signal.zone.zone_low:.2f}-{signal.zone.zone_high:.2f} | "
            f"Confidence: {signal.confidence:.2%} | "
            f"Quality: {signal.zone.quality_score:.1f} | "
            f"Position: {position_size:.2%}"
        )

    def _log_analysis_results(self, zones: List[Zone], signals: List[TradingSignal]):
        app_logger.info(f"Analysis: {len(zones)} zones, {len(signals)} signals")

        for zone in sorted(zones, key=lambda z: z.quality_score, reverse=True)[:3]:
            app_logger.debug(
                f"Zone: {zone.zone_type.value} {zone.zone_low:.2f}-{zone.zone_high:.2f} | "
                f"Touches: {zone.touches} | Quality: {zone.quality_score:.1f}"
            )
