# detectors.py
import numpy as np
from scipy import stats
from typing import List, Dict
from datetime import datetime
from models import Zone, ZoneType, MarketState
from logger import app_logger
from config import config


class ZoneDetector:
    def __init__(self):
        self.atr_period = config.ZONE_ATR_PERIOD
        self.min_touches = config.ZONE_MIN_TOUCHES

    def detect_zones(self, market_state: MarketState) -> List[Zone]:
        candles = list(market_state.candles_1m)
        if len(candles) < 7:
            return []

        zones = []

        for i in range(3, len(candles) - 3):
            window = candles[i - 3 : i + 4]
            current_low = candles[i]["low"]
            current_high = candles[i]["high"]

            if current_low == min(c["low"] for c in window):
                self._add_or_update_zone(
                    zones,
                    ZoneType.SUPPORT,
                    current_low,
                    config.ZONE_TOLERANCE_PCT,
                    candles[i].get("timestamp", datetime.now()),
                )

            if current_high == max(c["high"] for c in window):
                self._add_or_update_zone(
                    zones,
                    ZoneType.RESISTANCE,
                    current_high,
                    config.ZONE_TOLERANCE_PCT,
                    candles[i].get("timestamp", datetime.now()),
                )

        zones = [z for z in zones if z.touches >= self.min_touches]
        zones = self._statistical_validation(zones, candles)

        app_logger.debug(f"Detected {len(zones)} zones")
        return zones

    def _add_or_update_zone(
        self,
        zones: List[Zone],
        zone_type: ZoneType,
        price: float,
        tolerance: float,
        timestamp: datetime,
    ):
        for zone in zones:
            if (
                zone.zone_type == zone_type
                and abs(zone.center - price) / price <= tolerance
            ):
                zone.update_touch(price, timestamp)
                return

        new_zone = Zone(
            zone_type=zone_type,
            center=price,
            zone_low=price * (1 - config.ZONE_WIDTH_ATR_MULTIPLIER * 0.01),
            zone_high=price * (1 + config.ZONE_WIDTH_ATR_MULTIPLIER * 0.01),
            touches=1,
            touch_prices=[price],
            touch_times=[timestamp],
        )
        zones.append(new_zone)

    def _statistical_validation(
        self, zones: List[Zone], candles: List[Dict]
    ) -> List[Zone]:
        if not zones or len(candles) < 20:
            return zones

        all_prices = [c["close"] for c in candles[-100:]]

        valid_zones = []
        for zone in zones:
            if len(zone.touch_prices) >= 3:
                t_stat, p_value = stats.ttest_1samp(
                    zone.touch_prices, np.mean(all_prices)
                )
                zone.stats.p_value = p_value
                zone.stats.confidence = 1 - p_value

            if zone.stats.p_value < 0.1:
                valid_zones.append(zone)
            else:
                app_logger.debug(f"Zone filtered by p-value: {zone.stats.p_value:.4f}")

        return valid_zones
