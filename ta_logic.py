import pandas as pd
import numpy as np
from sklearn.cluster import DBSCAN
from signal_generator import SignalGenerator
from config import config, logger


class ZoneEngine:
    def __init__(self):
        self.sg = SignalGenerator()

    def get_zones(self, history):
        if len(history) < 20:
            return []
        df = pd.DataFrame(history)
        pivots = df[
            (df["h"] == df["h"].rolling(5, center=True).max())
            | (df["l"] == df["l"].rolling(5, center=True).min())
        ].copy()
        if pivots.empty:
            return []

        atr = (df["h"] - df["l"]).rolling(14).mean().iloc[-1]
        model = DBSCAN(eps=atr * config.CLUSTER_EPS_MULT, min_samples=2).fit(
            pivots[["h", "l"]].values.reshape(-1, 1)
        )
        pivots["cluster"] = model.labels_

        zones = []
        for cid in set(model.labels_):
            if cid == -1:
                continue
            c = pivots[pivots["cluster"] == cid]
            zones.append(
                {
                    "level": float(c[["h", "l"]].mean().mean()),
                    "top": float(c["h"].max()),
                    "bottom": float(c["l"].min()),
                }
            )
        return zones

    async def get_signal(self, db):
        h15 = await db.get_history(config.TF_ENTRY)
        h60 = await db.get_history(config.TF_LEVEL)
        h240 = await db.get_history(config.TF_TREND)

        if not (h15 and h60 and h240):
            return None

        # Тренд 4h
        trend = (
            "UP"
            if h240[-1]["c"] > pd.DataFrame(h240)["c"].ewm(span=21).mean().iloc[-1]
            else "DOWN"
        )
        # Зоны 1h
        zones = self.get_zones(h60)
        # Паттерн 15m
        pattern = self.sg.check_engulfing(pd.DataFrame(h15))

        price = h15[-1]["c"]
        if pattern and trend:
            for z in zones:
                if z["bottom"] <= price <= z["top"]:
                    if (pattern == "BUY" and trend == "UP") or (
                        pattern == "SELL" and trend == "DOWN"
                    ):
                        return {
                            "symbol": config.SYMBOL,
                            "side": pattern,
                            "price": price,
                            "type": "ZONE_3TF",
                        }
        return None
