# multi_symbol_manager.py
import asyncio
import json
import redis
from typing import Dict, List
from datetime import datetime
from collections import defaultdict
import asyncio
from concurrent.futures import ThreadPoolExecutor

from symbol_analyzer import SymbolAnalyzer
from logger import app_logger, perf_logger
from config import config


class MultiSymbolManager:
    """Управление анализом множества символов с асинхронной обработкой"""

    def __init__(self):
        self.symbol_analyzers: Dict[str, SymbolAnalyzer] = {}
        self.message_queue: asyncio.Queue = asyncio.Queue(maxsize=100000)
        self.processing_tasks: Dict[str, asyncio.Task] = {}

        # Инициализация анализаторов для всех символов
        for symbol in config.symbols:
            self.symbol_analyzers[symbol] = SymbolAnalyzer(symbol)

        # Семафор для ограничения параллельной обработки
        self.semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_SYMBOLS)

        # Статистика
        self.stats = {
            "messages_processed": 0,
            "messages_dropped": 0,
            "avg_queue_size": 0,
            "start_time": datetime.now(),
        }

        app_logger.info(f"Initialized manager for {len(config.symbols)} symbols")

    async def start(self, redis_client: redis.Redis):
        """Запуск менеджера"""
        # Запускаем consumer для обработки сообщений
        consumer_task = asyncio.create_task(self._message_consumer())

        # Запускаем producer (чтение из Redis)
        producer_task = asyncio.create_task(self._redis_producer(redis_client))

        # Запускаем мониторинг
        monitor_task = asyncio.create_task(self._performance_monitor())

        try:
            await asyncio.gather(consumer_task, producer_task, monitor_task)
        except asyncio.CancelledError:
            app_logger.info("Manager shutting down...")
        finally:
            # Очистка
            consumer_task.cancel()
            producer_task.cancel()
            monitor_task.cancel()

    async def _redis_producer(self, redis_client: redis.Redis):
        """Чтение сообщений из Redis и помещение в очередь"""
        pubsub = redis_client.pubsub()

        # Подписываемся на все каналы для всех символов и ТФ
        channels = []
        for symbol in config.symbols:
            for tf in config.timeframes:
                channels.append(f"kline.{tf}.{symbol}")
            channels.append(f"orderbook.50.{symbol}")
            channels.append(f"publicTrade.{symbol}")

        pubsub.subscribe(*channels)
        app_logger.info(f"Subscribed to {len(channels)} channels")

        try:
            for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        # Пытаемся положить в очередь (неблокирующе)
                        try:
                            self.message_queue.put_nowait(message)
                        except asyncio.QueueFull:
                            self.stats["messages_dropped"] += 1
                            if self.stats["messages_dropped"] % 100 == 0:
                                app_logger.warning(
                                    f"Queue full, dropped {self.stats['messages_dropped']} messages"
                                )

                    except Exception as e:
                        app_logger.error(f"Producer error: {e}")

        except Exception as e:
            app_logger.error(f"Redis producer error: {e}")
        finally:
            pubsub.close()

    async def _message_consumer(self):
        """Асинхронная обработка сообщений из очереди"""
        while True:
            try:
                message = await self.message_queue.get()

                # Обработка с ограничением параллелизма
                async with self.semaphore:
                    await self._process_single_message(message)

                self.message_queue.task_done()
                self.stats["messages_processed"] += 1

                # Обновляем средний размер очереди
                self.stats["avg_queue_size"] = (
                    self.stats["avg_queue_size"] * 0.99
                    + self.message_queue.qsize() * 0.01
                )

            except asyncio.CancelledError:
                break
            except Exception as e:
                app_logger.error(f"Consumer error: {e}")

    async def _process_single_message(self, message):
        """Обработка одного сообщения"""
        try:
            topic = message["channel"].decode()
            data = json.loads(message["data"].decode())

            # Парсим топик: kline.1.BTCUSDT -> (type, timeframe, symbol)
            parts = topic.split(".")

            if len(parts) >= 3:
                msg_type = parts[0]  # kline, orderbook, publicTrade
                symbol = parts[-1]  # последняя часть - символ

                if symbol in self.symbol_analyzers:
                    analyzer = self.symbol_analyzers[symbol]

                    if msg_type == "kline":
                        timeframe = parts[1]  # 1, 5, 60 и т.д.

                        # Извлекаем данные свечи
                        kline_data = data.get("data", [])
                        if kline_data:
                            k = kline_data[0]
                            candle = {
                                "open": float(k["open"]),
                                "high": float(k["high"]),
                                "low": float(k["low"]),
                                "close": float(k["close"]),
                                "volume": float(k["volume"]),
                            }

                            # Запускаем обработку свечи
                            await analyzer.process_candle(timeframe, candle)

                    elif msg_type == "orderbook":
                        # Обработка стакана
                        orderbook_data = data.get("data", {})
                        if orderbook_data:
                            analyzer.market_states["1"].orderbook = {
                                "bids": orderbook_data.get("b", []),
                                "asks": orderbook_data.get("a", []),
                            }

                    elif msg_type == "publicTrade":
                        # Обработка сделок
                        trades_data = data.get("data", [])
                        for trade in trades_data:
                            analyzer.market_states["1"].recent_trades.append(
                                {
                                    "price": float(trade["p"]),
                                    "qty": float(trade["v"]),
                                    "side": trade.get("S", "unknown"),
                                    "timestamp": datetime.now(),
                                }
                            )

        except Exception as e:
            app_logger.error(f"Message processing error: {e}")

    async def _performance_monitor(self):
        """Мониторинг производительности"""
        while True:
            try:
                await asyncio.sleep(60)  # Каждую минуту

                total_signals = sum(
                    a.performance_stats["total_signals"]
                    for a in self.symbol_analyzers.values()
                )

                perf_logger.info(
                    f"PERF | Symbols: {len(self.symbol_analyzers)} | "
                    f"Queue: {self.message_queue.qsize()}/{self.stats['avg_queue_size']:.1f} | "
                    f"Processed: {self.stats['messages_processed']} | "
                    f"Dropped: {self.stats['messages_dropped']} | "
                    f"Signals: {total_signals}"
                )

                # Детальная статистика по символам (раз в 5 минут)
                if datetime.now().minute % 5 == 0:
                    for symbol, analyzer in self.symbol_analyzers.items():
                        stats = analyzer.get_performance_stats()
                        if stats["active_zones_total"] > 0:
                            perf_logger.debug(
                                f"SYMBOL {symbol} | "
                                f"Zones: {stats['active_zones_total']} | "
                                f"Signals: {stats['total_signals']} | "
                                f"Avg time: {stats['avg_processing_time']:.1f}ms"
                            )

            except asyncio.CancelledError:
                break
            except Exception as e:
                app_logger.error(f"Monitor error: {e}")

    async def stop(self):
        """Корректная остановка"""
        for task in self.processing_tasks.values():
            task.cancel()

        await asyncio.gather(*self.processing_tasks.values(), return_exceptions=True)
