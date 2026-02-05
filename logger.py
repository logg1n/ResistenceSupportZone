# logger.py
from loguru import logger
import sys
from pathlib import Path
from config import config

# Создаем папку для логов
log_path = Path("logs")
log_path.mkdir(exist_ok=True)


# Конфигурация loguru
def setup_logger():
    # Удаляем стандартный handler
    logger.remove()

    # Console logging (только INFO и выше)
    logger.add(
        sys.stdout,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=config.LOG_LEVEL,
        colorize=True,
    )

    # Основной лог файл
    logger.add(
        log_path / "app.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="INFO",
        rotation=config.LOG_ROTATION,
        retention=config.LOG_RETENTION,
        compression="zip",
    )

    # Лог ошибок
    logger.add(
        log_path / "errors.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="ERROR",
        rotation=config.LOG_ROTATION,
        retention=config.LOG_RETENTION,
    )

    # Лог сигналов (отдельный файл)
    logger.add(
        log_path / "signals.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | SIGNAL | {message}",
        level="INFO",
        rotation=config.LOG_ROTATION,
        retention=config.LOG_RETENTION,
        filter=lambda record: "signal" in record["extra"],
    )

    # Лог производительности
    logger.add(
        log_path / "performance.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | PERFORMANCE | {message}",
        level="DEBUG",
        rotation=config.LOG_ROTATION,
        retention=config.LOG_RETENTION,
        filter=lambda record: "performance" in record["extra"],
    )

    return logger


# Создаем специализированные логгеры
app_logger = setup_logger()
signal_logger = app_logger.bind(signal=True)
perf_logger = app_logger.bind(performance=True)
