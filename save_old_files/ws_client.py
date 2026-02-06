#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebSocket клиент для сбора данных с Bybit
Исправленная версия с правильной обработкой ответов
"""

import asyncio
import json
import websockets
import redis
import argparse
import sys
from typing import List, Dict, Any
from datetime import datetime
from dataclasses import dataclass, field
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class WSConfig:
    """Конфигурация WebSocket клиента"""

    WS_URL: str = "wss://stream.bybit.com/v5/public/linear"
    PING_INTERVAL: int = 20
    BATCH_SIZE: int = 10
    BATCH_DELAY: float = 0.5
    RECONNECT_DELAY: int = 5
    CONNECT_TIMEOUT: int = 10
    MAX_RECONNECT_ATTEMPTS: int = 100


class BybitWebSocketClient:
    """Клиент WebSocket для Bybit (исправленная версия)"""

    def __init__(
        self,
        symbols: List[str],
        timeframes: List[str],
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 0,
    ):
        self.config = WSConfig()
        self.symbols = symbols
        self.timeframes = timeframes

        # Инициализация Redis клиента (без устаревших параметров)
        self.redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            decode_responses=False,
            socket_connect_timeout=5,
        )

        # Статистика
        self.stats = {
            "messages_received": 0,
            "messages_published": 0,
            "errors": 0,
            "reconnects": 0,
            "start_time": datetime.now(),
            "subscriptions_ok": 0,
        }

        self.running = False
        self.websocket = None

        logger.info(f"Инициализирован клиент для {len(symbols)} символов: {symbols}")
        logger.info(f"Таймфреймы: {timeframes}")

    def _generate_subscriptions(self) -> List[str]:
        """Генерация списка каналов для подписки"""
        subscriptions = []

        for symbol in self.symbols:
            for timeframe in self.timeframes:
                subscriptions.append(f"kline.{timeframe}.{symbol}")

            subscriptions.append(f"publicTrade.{symbol}")
            subscriptions.append(f"orderbook.50.{symbol}")

        logger.debug(f"Сгенерировано {len(subscriptions)} каналов для подписки")
        return subscriptions

    async def _subscribe_to_channels(self) -> bool:
        """Подписка на каналы WebSocket (исправленная)"""
        subscriptions = self._generate_subscriptions()

        if not subscriptions:
            logger.warning("Нет каналов для подписки")
            return False

        logger.info(f"Подписываюсь на {len(subscriptions)} каналов...")

        # Подписываемся одним сообщением (Bybit поддерживает до 10)
        if len(subscriptions) > 10:
            logger.warning(
                f"Слишком много каналов ({len(subscriptions)}), берем первые 10"
            )
            subscriptions = subscriptions[:10]

        try:
            # Формируем сообщение подписки
            subscribe_msg = {"op": "subscribe", "args": subscriptions}

            # Отправляем подписку
            await self.websocket.send(json.dumps(subscribe_msg))
            logger.info(f"Отправлена подписка на {len(subscriptions)} каналов")

            # Ждем ответ (первое сообщение после подписки)
            # Bybit может сначала прислать данные, потом подтверждение
            await asyncio.sleep(1)

            logger.info(f"✅ Предположительно подписан на {len(subscriptions)} каналов")
            self.stats["subscriptions_ok"] = len(subscriptions)
            return True

        except Exception as e:
            logger.error(f"Ошибка подписки: {e}")
            return False

    async def _process_message(self, message: str):
        """Обработка входящего сообщения WebSocket"""
        try:
            data = json.loads(message)

            # Определяем тип сообщения
            if "op" in data:
                # Это системное сообщение
                op = data["op"]
                if op == "subscribe":
                    if data.get("success", False):
                        logger.info(
                            f"✅ Подтверждение подписки: {data.get('args', [])}"
                        )
                    else:
                        logger.error(f"❌ Ошибка подписки: {data}")
                elif op == "pong":
                    logger.debug("Получен pong")
                return

            # Это рыночные данные
            topic = data.get("topic", "")

            if topic:
                # Публикуем в Redis
                self.redis_client.publish(topic, message.encode("utf-8"))

                # Обновляем статистику
                self.stats["messages_received"] += 1
                self.stats["messages_published"] += 1

                # Логируем первое сообщение каждого типа
                if self.stats["messages_received"] <= 10:
                    data_type = (
                        "свечи"
                        if "kline" in topic
                        else "сделки" if "trade" in topic else "стакан"
                    )
                    logger.debug(f"📨 Первое сообщение {data_type}: {topic}")

        except json.JSONDecodeError as e:
            logger.error(f"Ошибка декодирования JSON: {e}")
            self.stats["errors"] += 1
        except redis.RedisError as e:
            logger.error(f"Ошибка Redis: {e}")
            self.stats["errors"] += 1
        except Exception as e:
            logger.error(f"Неизвестная ошибка: {e}")
            self.stats["errors"] += 1

    async def _connection_handler(self):
        """Основной обработчик соединения WebSocket (исправленный)"""
        reconnect_attempt = 0

        while self.running and reconnect_attempt < self.config.MAX_RECONNECT_ATTEMPTS:
            try:
                logger.info(
                    f"Подключение к WebSocket... (попытка {reconnect_attempt + 1})"
                )

                # Подключаемся к WebSocket
                async with websockets.connect(
                    self.config.WS_URL,
                    ping_interval=None,  # Отключаем авто-пинг
                    close_timeout=1,
                ) as websocket:

                    self.websocket = websocket
                    logger.info("✅ Подключение к Bybit установлено")

                    # Подписываемся на каналы
                    if not await self._subscribe_to_channels():
                        logger.warning("Проблема с подпиской, продолжаем...")

                    # Сбрасываем счетчик переподключений
                    reconnect_attempt = 0

                    # Основной цикл обработки сообщений
                    while self.running:
                        try:
                            # Получаем сообщение
                            message = await asyncio.wait_for(
                                websocket.recv(), timeout=30  # Таймаут 30 секунд
                            )

                            # Обрабатываем сообщение
                            await self._process_message(message)

                        except asyncio.TimeoutError:
                            # Таймаут - отправляем ping для поддержания соединения
                            try:
                                await websocket.send(json.dumps({"op": "ping"}))
                                logger.debug("Отправлен ping")
                            except Exception as e:
                                logger.warning(f"Ошибка при отправке ping: {e}")
                                break

                        except websockets.exceptions.ConnectionClosed as e:
                            logger.warning(f"Соединение закрыто: {e}")
                            break

                        except Exception as e:
                            logger.error(f"Ошибка в цикле обработки: {e}")
                            break

            except Exception as e:
                logger.error(f"Ошибка подключения: {e}")

            # Если соединение разорвано
            if self.running:
                reconnect_attempt += 1
                self.stats["reconnects"] += 1

                logger.warning(
                    f"Переподключение через {self.config.RECONNECT_DELAY} сек "
                    f"(попытка {reconnect_attempt}/{self.config.MAX_RECONNECT_ATTEMPTS})"
                )

                await asyncio.sleep(self.config.RECONNECT_DELAY)

    async def _stats_monitor(self):
        """Мониторинг статистики"""
        while self.running:
            await asyncio.sleep(30)  # Каждые 30 секунд

            elapsed = (datetime.now() - self.stats["start_time"]).total_seconds()
            rate = self.stats["messages_received"] / elapsed if elapsed > 0 else 0

            logger.info(
                f"📈 СТАТИСТИКА | "
                f"Сообщений: {self.stats['messages_received']} | "
                f"Опубликовано: {self.stats['messages_published']} | "
                f"Ошибок: {self.stats['errors']} | "
                f"Переподкл: {self.stats['reconnects']} | "
                f"Скорость: {rate:.1f}/сек"
            )

            # Если долго нет сообщений
            if self.stats["messages_received"] == 0 and elapsed > 60:
                logger.warning("⚠️  Нет входящих сообщений более 60 секунд")

    async def start(self):
        """Запуск клиента"""
        if self.running:
            logger.warning("Клиент уже запущен")
            return

        logger.info("🚀 Запуск WebSocket клиента...")
        self.running = True

        # Проверяем подключение к Redis
        try:
            self.redis_client.ping()
            logger.info("✅ Подключение к Redis: OK")
        except redis.ConnectionError:
            logger.error("❌ Не удалось подключиться к Redis")
            self.running = False
            return

        # Запускаем задачи
        try:
            await asyncio.gather(self._connection_handler(), self._stats_monitor())
        except asyncio.CancelledError:
            logger.info("Задачи отменены")
        finally:
            await self.stop()

    async def stop(self):
        """Остановка клиента"""
        if not self.running:
            return

        logger.info("🛑 Остановка WebSocket клиента...")
        self.running = False

        # Закрываем Redis
        try:
            self.redis_client.close()
        except:
            pass

        # Итоговая статистика
        elapsed = (datetime.now() - self.stats["start_time"]).total_seconds()
        logger.info(
            f"📊 ИТОГО: {self.stats['messages_received']} сообщений за {elapsed:.1f} сек"
        )


def parse_arguments():
    """Парсинг аргументов командной строки"""
    parser = argparse.ArgumentParser(
        description="WebSocket клиент для сбора данных с Bybit"
    )

    parser.add_argument(
        "--symbols",
        "-s",
        nargs="+",
        default=["BTCUSDT"],
        help="Торговые пары (по умолчанию: BTCUSDT)",
    )

    parser.add_argument(
        "--timeframes",
        "-t",
        nargs="+",
        choices=[
            "1",
            "3",
            "5",
            "15",
            "30",
            "60",
            "120",
            "240",
            "360",
            "720",
            "D",
            "W",
            "M",
        ],
        default=["1", "5", "60"],
        help="Таймфреймы (1=1m, 60=1h и т.д.)",
    )

    parser.add_argument(
        "--redis-host", default="localhost", help="Хост Redis (по умолчанию: localhost)"
    )

    parser.add_argument(
        "--redis-port", type=int, default=6379, help="Порт Redis (по умолчанию: 6379)"
    )

    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Уровень логирования",
    )

    parser.add_argument(
        "--test-mode", action="store_true", help="Тестовый режим (BTC на 1m)"
    )

    return parser.parse_args()


def main():
    """Основная функция"""
    args = parse_arguments()

    # Настройка логирования
    logging.getLogger().setLevel(getattr(logging, args.log_level))

    # Определяем конфигурацию
    if args.test_mode:
        symbols = ["BTCUSDT"]
        timeframes = ["1"]
        logger.info("🛠️  Тестовый режим: BTCUSDT на 1m")
    else:
        symbols = args.symbols
        timeframes = args.timeframes

    # Выводим информацию
    print("\n" + "=" * 60)
    print("🛰️  BYBIT WEBSOCKET DATA FEED v2.1")
    print("=" * 60)
    print(f"📊 Символы: {', '.join(symbols)}")
    print(f"⏱️  Таймфреймы: {', '.join(timeframes)}")
    print(f"📡 Redis: {args.redis_host}:{args.redis_port}")
    print("=" * 60 + "\n")

    # Создаем и запускаем клиент
    client = BybitWebSocketClient(
        symbols=symbols,
        timeframes=timeframes,
        redis_host=args.redis_host,
        redis_port=args.redis_port,
    )

    try:
        asyncio.run(client.start())
    except KeyboardInterrupt:
        print("\n👋 Остановка по запросу пользователя")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
