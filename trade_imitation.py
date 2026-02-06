import asyncio
import json
from loguru import logger
from db_storage import RedisClient
from config import config


class TradeImitation:
    def __init__(self, db: RedisClient):
        self.db = db
        self.active_trades = []
        self.rr = 3.0  # Твой риск-ревард 3:1
        self.stats = {"wins": 0, "losses": 0, "profit": 0.0}

    def open_position(self, signal: dict):
        """Логика открытия из сигнала (унифицировано под OracleCandles)"""
        entry = signal["price"]
        side = signal["side"]

        # Рассчитываем стоп (0.5% для примера, либо берем из metadata)
        sl_dist = entry * 0.005
        sl = entry - sl_dist if side == "BUY" else entry + sl_dist

        # Тейк строго 3:1
        tp = (
            entry + (abs(entry - sl) * self.rr)
            if side == "BUY"
            else entry - (abs(entry - sl) * self.rr)
        )

        trade = {
            "side": side,
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "symbol": signal.get("symbol", config.SYMBOL),
            "source": signal.get("type", "UNKNOWN"),
        }

        self.active_trades.append(trade)
        logger.warning(
            f"🔔 NEW TRADE [{trade['source']}]: {side} at {entry:.2f} | TP: {tp:.2f} | SL: {sl:.2f}"
        )

    async def monitor_market(self):
        """Бесконечный цикл слежения за ценой в памяти"""
        logger.info("Мониторинг рынка запущен...")
        while True:
            # Получаем актуальную цену из Redis (куда её пишет WS)
            history = await self.db.get_history(f"{config.SYMBOL}:{config.TF_ENTRY}")
            if not history or not self.active_trades:
                await asyncio.sleep(1)
                continue

            current_price = history[-1]["c"]

            for trade in self.active_trades[:]:
                closed = False
                if trade["side"] == "BUY":
                    if current_price >= trade["tp"]:
                        self.stats["wins"] += 1
                        logger.success(
                            f"✅ PROFIT (3:1): {trade['side']} | Price: {current_price}"
                        )
                        closed = True
                    elif current_price <= trade["sl"]:
                        self.stats["losses"] += 1
                        logger.error(
                            f"❌ STOP LOSS: {trade['side']} | Price: {current_price}"
                        )
                        closed = True

                elif trade["side"] == "SELL":
                    if current_price <= trade["tp"]:
                        self.stats["wins"] += 1
                        logger.success(
                            f"✅ PROFIT (3:1): {trade['side']} | Price: {current_price}"
                        )
                        closed = True
                    elif current_price >= trade["sl"]:
                        self.stats["losses"] += 1
                        logger.error(
                            f"❌ STOP LOSS: {trade['side']} | Price: {current_price}"
                        )
                        closed = True

                if closed:
                    self.active_trades.remove(trade)
                    total = self.stats["wins"] + self.stats["losses"]
                    logger.info(
                        f"📊 Stats: Wins: {self.stats['wins']} | Losses: {self.stats['losses']} | WR: {(self.stats['wins']/total)*100:.1f}%"
                    )

            await asyncio.sleep(1)  # Проверка раз в секунду

    async def listen_signals(self):
        """Слушает очередь сигналов из Redis"""
        logger.info("Ожидание сигналов из Redis (trading_signals)...")
        while True:
            # RPOP — блокирующее или обычное извлечение из очереди
            signal_data = await self.db.pop_signal()
            if signal_data:
                self.open_position(signal_data)
            await asyncio.sleep(0.5)


async def main():
    db = RedisClient()
    imitator = TradeImitation(db)

    # Запускаем две задачи параллельно: мониторинг и прослушку очереди
    await asyncio.gather(imitator.listen_signals(), imitator.monitor_market())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
