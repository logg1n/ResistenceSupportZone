# config.py
import argparse
from dataclasses import dataclass, field
from typing import List, Dict, Optional
import sys


@dataclass
class Config:
    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    # Символы по умолчанию
    DEFAULT_SYMBOLS: List[str] = field(
        default_factory=lambda: [
            "BTCUSDT",
            "ETHUSDT",
            "BNBUSDT",
            "SOLUSDT",
            "XRPUSDT",
            "ADAUSDT",
            "AVAXUSDT",
            "DOTUSDT",
            "DOGEUSDT",
            "LINKUSDT",
        ]
    )

    # Таймфреймы по умолчанию
    DEFAULT_TIMEFRAMES: List[str] = field(
        default_factory=lambda: ["1", "5", "15", "60", "240"]
    )

    # CLI-аргументы будут здесь
    symbols: List[str] = field(default_factory=list)
    timeframes: List[str] = field(default_factory=list)

    # Параметры зон
    ZONE_ATR_PERIOD: int = 14
    ZONE_MIN_TOUCHES: int = 3
    ZONE_TOLERANCE_PCT: float = 0.003
    ZONE_WIDTH_ATR_MULTIPLIER: float = 0.5

    # Сигналы
    MIN_CONFIDENCE: float = 0.7
    ACCOUNT_RISK_PERCENT: float = 0.02

    # Параллельная обработка
    MAX_CONCURRENT_SYMBOLS: int = 5
    ANALYSIS_INTERVAL_SECONDS: Dict[str, int] = field(
        default_factory=lambda: {"1": 5, "5": 30, "15": 60, "60": 300, "240": 900}
    )

    # Логирование
    LOG_LEVEL: str = "INFO"
    LOG_ROTATION: str = "10 MB"
    LOG_RETENTION: str = "7 days"

    # Размеры буферов
    MAX_CANDLES_PER_TF: Dict[str, int] = field(
        default_factory=lambda: {"1": 500, "5": 400, "15": 300, "60": 200, "240": 100}
    )


def parse_cli_args():
    """Парсинг аргументов командной строки"""
    parser = argparse.ArgumentParser(
        description="Multi-Symbol Support/Resistance Analyzer"
    )

    parser.add_argument("--symbols", "-s", nargs="+", help="Торговые пары")
    parser.add_argument("--timeframes", "-t", nargs="+", help="Таймфреймы")
    parser.add_argument("--all-symbols", action="store_true", help="Все символы")
    parser.add_argument("--all-timeframes", action="store_true", help="Все ТФ")
    parser.add_argument("--test-mode", action="store_true", help="Тестовый режим")
    parser.add_argument("--list-symbols", action="store_true", help="Список символов")
    parser.add_argument("--redis-host", default="localhost", help="Redis хост")
    parser.add_argument("--redis-port", type=int, default=6379, help="Redis порт")
    parser.add_argument(
        "--max-concurrent", type=int, default=5, help="Макс. параллельных"
    )
    parser.add_argument("--log-level", default="INFO", help="Уровень логирования")

    return parser.parse_args()


def create_config():
    """Создание конфига с учетом CLI аргументов"""
    args = parse_cli_args()

    # Если запрошен список символов
    if args.list_symbols:
        config = Config()
        print("📊 Доступные символы:")
        for symbol in config.DEFAULT_SYMBOLS:
            print(f"  • {symbol}")
        print(f"\nВсего: {len(config.DEFAULT_SYMBOLS)} символов")
        sys.exit(0)

    # Определяем символы
    if args.test_mode:
        symbols = ["BTCUSDT"]
    elif args.symbols:
        symbols = args.symbols
    elif args.all_symbols:
        config = Config()
        symbols = config.DEFAULT_SYMBOLS
    else:
        config = Config()
        symbols = config.DEFAULT_SYMBOLS[:3]  # Первые 3 по умолчанию

    # Определяем таймфреймы
    if args.test_mode:
        timeframes = ["1"]
    elif args.timeframes:
        timeframes = args.timeframes
    elif args.all_timeframes:
        config = Config()
        timeframes = config.DEFAULT_TIMEFRAMES
    else:
        config = Config()
        timeframes = ["1", "5", "15"]  # Основные ТФ

    # Создаем финальный конфиг
    config = Config()
    config.symbols = symbols
    config.timeframes = timeframes
    config.MAX_CONCURRENT_SYMBOLS = args.max_concurrent
    config.LOG_LEVEL = args.log_level
    config.REDIS_HOST = args.redis_host
    config.REDIS_PORT = args.redis_port

    return config, args


# Глобальные переменные
config, cli_args = create_config()
