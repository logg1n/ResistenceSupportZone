import asyncio
import json
import websockets
from db_storage import RedisClient
from config import config, logger


class BybitDataStream:
    def __init__(self, db: RedisClient):
        self.db = db
        self.url = "wss://stream.bybit.com/v5/public/linear"
        self.is_running = True

    async def _send_ping(self, ws):
        """Отправка пинга каждые 20 секунд для поддержания сессии"""
        while self.is_running:
            try:
                await ws.send(json.dumps({"op": "ping"}))
                # logger.debug("WS Ping sent")
                await asyncio.sleep(20)
            except Exception:
                break

    async def _subscribe(self, ws):
        """Подписка на нужные таймфреймы"""
        intervals = [config.TF_ENTRY, config.TF_LEVEL, config.TF_TREND]
        args = [f"kline.{tf}.{config.SYMBOL}" for tf in intervals]

        subscribe_msg = {"op": "subscribe", "args": args}
        await ws.send(json.dumps(subscribe_msg))
        logger.info(f"Subscribed to: {args}")

    async def connect(self):
        """Основной цикл подключения с авто-реконнектом"""
        while self.is_running:
            try:
                async with websockets.connect(self.url) as ws:
                    logger.info("Connected to Bybit WebSockets")

                    # Запускаем пинг и подписку
                    await self._subscribe(ws)
                    ping_task = asyncio.create_task(self._send_ping(ws))

                    while self.is_running:
                        msg = await ws.recv()
                        data = json.loads(msg)

                        # Обработка данных свечи
                        if "data" in data:
                            # По структуре Bybit V5 data - это список
                            kline_data = data["data"][0]
                            if kline_data.get("confirm"):
                                # Извлекаем ТФ из топика "kline.5.BTCUSDT"
                                tf = data["topic"].split(".")[1]

                                candle = {
                                    "t": int(kline_data["start"]),
                                    "o": float(kline_data["open"]),
                                    "h": float(kline_data["high"]),
                                    "l": float(kline_data["low"]),
                                    "c": float(kline_data["close"]),
                                    "v": float(kline_data["volume"]),
                                }

                                await self.db.push_candle(tf, candle)
                                logger.info(f"✅ Candle {tf} confirmed: {candle['c']}")

            except Exception as e:
                logger.error(f"WS Connection lost: {e}. Reconnecting in 5s...")
                await asyncio.sleep(5)

    def stop(self):
        self.is_running = False
