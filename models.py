# models.py
import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Deque
from collections import deque
from datetime import datetime
from enum import Enum
from logger import app_logger


class ZoneType(Enum):
    SUPPORT = "support"
    RESISTANCE = "resistance"


@dataclass
class StatisticalMetrics:
    p_value: float = 1.0
    confidence: float = 0.0
    z_score: float = 0.0
    touches_std: float = 0.0
    persistence_score: float = 0.0
    created: datetime = field(default_factory=datetime.now)
    last_touch: datetime = field(default_factory=datetime.now)

    def decay_factor(self, half_life_hours: float = 12.0) -> float:
        age_hours = (datetime.now() - self.created).total_seconds() / 3600
        return np.exp(-np.log(2) * age_hours / half_life_hours)

    def recency_factor(self) -> float:
        hours_since_touch = (datetime.now() - self.last_touch).total_seconds() / 3600
        return max(0, 1.0 - hours_since_touch / 24.0)


@dataclass
class Zone:
    zone_type: ZoneType
    center: float
    zone_low: float
    zone_high: float
    touches: int = 0
    touch_prices: List[float] = field(default_factory=list)
    touch_times: List[datetime] = field(default_factory=list)
    stats: StatisticalMetrics = field(default_factory=StatisticalMetrics)

    confirmed_tf: Dict[str, bool] = field(default_factory=dict)
    orderbook_strength: Optional[float] = None
    volume_strength: Optional[float] = None
    trade_flow_strength: Optional[float] = None
    successful_rejections: int = 0
    failed_breakouts: int = 0

    @property
    def quality_score(self) -> float:
        score = 0.0
        score += min(self.touches * 8, 20)
        score += (
            20
            if self.stats.confidence > 0.95
            else 10 if self.stats.confidence > 0.9 else 0
        )

        tf_multiplier = sum(self.confirmed_tf.values()) / 3.0
        score += tf_multiplier * 15

        if self.orderbook_strength:
            score += min(self.orderbook_strength * 10, 10)
        if self.volume_strength:
            score += min(self.volume_strength * 10, 10)

        score += self.stats.recency_factor() * 5
        score += self.stats.decay_factor() * 5

        if self.touches > 0:
            win_rate = self.successful_rejections / self.touches
            score += win_rate * 10

        return min(100.0, score)

    def update_touch(self, price: float, time: datetime):
        self.touch_prices.append(price)
        self.touch_times.append(time)
        self.touches += 1
        self.stats.last_touch = time

        if len(self.touch_prices) >= 3:
            prices_array = np.array(self.touch_prices[-20:])
            self.stats.touches_std = np.std(prices_array)

            if len(self.touch_prices) > 5:
                self.stats.z_score = abs(
                    (price - np.mean(prices_array)) / max(np.std(prices_array), 0.001)
                )


# models.py - обновленная часть

@dataclass
class MarketState:
    """Состояние рынка для конкретного ТФ"""
    
    def __init__(self, max_candles: int = 500):
        self.candles: Deque[Dict] = deque(maxlen=max_candles)
        self.orderbook: Dict = {}
        self.recent_trades: Deque[Dict] = deque(maxlen=1000)
        self.active_zones: List[Zone] = []
    
    def add_candle(self, candle: Dict, timeframe: str):
        """Универсальный метод добавления свечи"""
        if not self._validate_candle(candle):
            app_logger.warning(f"Invalid candle for TF {timeframe}: {candle}")
            return
        
        candle['timestamp'] = datetime.now()
        self.candles.append(candle)
