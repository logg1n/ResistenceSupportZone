# confirmations.py
import numpy as np
from typing import Dict, List
from models import Zone, MarketState
from logger import app_logger


class ConfirmationSystem:
    @staticmethod
    def confirm_with_orderbook(zone: Zone, orderbook: Dict) -> float:
        if not orderbook or "bids" not in orderbook or "asks" not in orderbook:
            return 0.0

        bids = [(float(p), float(q)) for p, q in orderbook["bids"][:10]]
        asks = [(float(p), float(q)) for p, q in orderbook["asks"][:10]]

        total_volume = 0
        for price, volume in bids + asks:
            if zone.zone_low <= price <= zone.zone_high:
                total_volume += volume

        avg_volume = (
            sum(v for _, v in bids[:5] + asks[:5]) / 10 if len(bids + asks) >= 10 else 1
        )
        strength = min(total_volume / max(avg_volume, 1), 3.0) / 3.0

        if strength > 0.3:
            zone.orderbook_strength = strength

        return strength

    @staticmethod
    def confirm_with_volume(zone: Zone, recent_candles: List[Dict]) -> float:
        if not recent_candles or len(recent_candles) < 10:
            return 0.0

        touch_volumes = []
        for candle in recent_candles[-50:]:
            if (
                zone.zone_low <= candle["low"] <= zone.zone_high
                or zone.zone_low <= candle["high"] <= zone.zone_high
            ):
                touch_volumes.append(candle["volume"])

        if not touch_volumes:
            return 0.0

        avg_volume = np.mean([c["volume"] for c in recent_candles[-20:]])
        volume_ratio = np.mean(touch_volumes) / max(avg_volume, 1)
        strength = min(volume_ratio, 2.0) / 2.0

        if strength > 0.3:
            zone.volume_strength = strength

        return strength

    @staticmethod
    def confirm_multiple_timeframes(
        zone: Zone, market_state: MarketState
    ) -> Dict[str, bool]:
        confirmations = {}

        for tf_name, tf_candles in [
            ("5m", market_state.candles_5m),
            ("1h", market_state.candles_1h),
        ]:
            if len(tf_candles) < 10:
                confirmations[tf_name] = False
                continue

            touches = 0
            for candle in list(tf_candles)[-20:]:
                if zone.zone_low <= candle["low"] <= zone.zone_high:
                    touches += 1
                elif zone.zone_low <= candle["high"] <= zone.zone_high:
                    touches += 1

            confirmations[tf_name] = touches >= 2

        zone.confirmed_tf = confirmations
        return confirmations
