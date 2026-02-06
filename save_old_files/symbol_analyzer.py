# symbol_analyzer.py
import asyncio
from datetime import datetime
from typing import Dict, List, Set
import numpy as np

from models import MarketState, Zone
from detectors import ZoneDetector
from confirmations import ConfirmationSystem
from signals import SignalGenerator, TradingSignal
from logger import app_logger, signal_logger, perf_logger
from config import config


class SymbolAnalyzer:
    """Анализатор для одной торговой пары"""

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.market_states: Dict[str, MarketState] = {}
        self.zone_detectors: Dict[str, ZoneDetector] = {}
        self.signal_generators: Dict[str, SignalGenerator] = {}

        # Инициализация для каждого активного ТФ
        for tf in config.timeframes:
            self.market_states[tf] = MarketState(
                max_candles=config.MAX_CANDLES_PER_TF.get(tf, 200)
            )
            self.zone_detectors[tf] = ZoneDetector()
            self.signal_generators[tf] = SignalGenerator()

        # Таймеры для периодического анализа
        self.last_analysis_time: Dict[str, datetime] = {
            tf: datetime.now() for tf in config.timeframes
        }

        # Активные зоны по ТФ
        self.active_zones: Dict[str, List[Zone]] = {tf: [] for tf in config.timeframes}

        # Статистика
        self.performance_stats = {
            "total_signals": 0,
            "avg_processing_time": 0,
            "errors": 0,
        }

        app_logger.info(f"Initialized analyzer for {symbol}")

    async def process_candle(self, timeframe: str, candle_data: Dict):
        """Обработка свечи для конкретного ТФ"""
        start_time = datetime.now()

        try:
            if timeframe not in self.market_states:
                app_logger.warning(
                    f"Unsupported timeframe {timeframe} for {self.symbol}"
                )
                return

            # Добавляем свечу
            self.market_states[timeframe].add_candle(candle_data, timeframe)

            # Проверяем, нужно ли запускать анализ
            interval = config.ANALYSIS_INTERVAL_SECONDS.get(timeframe, 30)
            if (
                datetime.now() - self.last_analysis_time[timeframe]
            ).total_seconds() >= interval:
                await self._analyze_timeframe(timeframe)
                self.last_analysis_time[timeframe] = datetime.now()

        except Exception as e:
            self.performance_stats["errors"] += 1
            app_logger.error(f"Error processing {self.symbol}/{timeframe}: {e}")

        # Обновляем статистику
        proc_time = (datetime.now() - start_time).total_seconds() * 1000
        self.performance_stats["avg_processing_time"] = (
            self.performance_stats["avg_processing_time"] * 0.9 + proc_time * 0.1
        )

    async def _analyze_timeframe(self, timeframe: str):
        """Анализ зон для конкретного ТФ"""
        try:
            market_state = self.market_states[timeframe]

            # 1. Детекция зон на основном ТФ
            zones = self.zone_detectors[timeframe].detect_zones(market_state)

            # 2. Мультитаймфреймовое подтверждение
            confirmed_zones = []
            for zone in zones:
                # Подтверждение на старших ТФ
                for confirm_tf in config.CONFIRMATION_TIMEFRAMES:
                    if confirm_tf in self.market_states and confirm_tf != timeframe:
                        confirm_state = self.market_states[confirm_tf]
                        if ConfirmationSystem.confirm_across_timeframes(
                            zone, confirm_state
                        ):
                            zone.confirmed_tf[confirm_tf] = True

                # Дополнительные подтверждения
                if market_state.orderbook:
                    zone.orderbook_strength = ConfirmationSystem.confirm_with_orderbook(
                        zone, market_state.orderbook
                    )

                if len(market_state.candles) > 10:
                    zone.volume_strength = ConfirmationSystem.confirm_with_volume(
                        zone, list(market_state.candles)[-100:]
                    )

                if zone.quality_score >= 40:  # Фильтр по качеству
                    confirmed_zones.append(zone)

            # 3. Обновляем активные зоны
            self.active_zones[timeframe] = confirmed_zones

            # 4. Генерация сигналов (только для 1m и 5m)
            if timeframe in ["1", "5"]:
                signals = self.signal_generators[timeframe].generate_signals(
                    market_state, confirmed_zones
                )

                for signal in signals:
                    await self._handle_signal(signal, timeframe)

            # Логирование
            if confirmed_zones:
                app_logger.debug(
                    f"{self.symbol}/{timeframe}m: {len(confirmed_zones)} zones, "
                    f"top quality: {max(z.quality_score for z in confirmed_zones):.1f}"
                )

        except Exception as e:
            app_logger.error(f"Analysis error {self.symbol}/{timeframe}: {e}")

    async def _handle_signal(self, signal: TradingSignal, timeframe: str):
        """Обработка торгового сигнала"""
        position_size = signal.calculate_position_size()

        signal_logger.info(
            f"📈 {self.symbol} | {timeframe}m | {signal.signal_type.upper()} | "
            f"Zone: {signal.zone.zone_type.value} {signal.zone.zone_low:.2f}-{signal.zone.zone_high:.2f} | "
            f"Conf: {signal.confidence:.2%} | Qual: {signal.zone.quality_score:.1f} | "
            f"Pos: {position_size:.2%}"
        )

        self.performance_stats["total_signals"] += 1

        # Здесь можно добавить отправку ордера
        # await self.send_order(signal, position_size)

    def get_performance_stats(self) -> Dict:
        """Получение статистики производительности"""
        return {
            "symbol": self.symbol,
            **self.performance_stats,
            "active_zones_total": sum(
                len(zones) for zones in self.active_zones.values()
            ),
        }
