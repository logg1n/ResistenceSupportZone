# main.py
import asyncio
import signal
import sys
import redis

from multi_symbol_manager import MultiSymbolManager
from logger import app_logger
from config import config


async def shutdown(manager, loop):
    """Корректное завершение"""
    app_logger.info("Shutdown initiated...")

    # Остановка менеджера
    await manager.stop()

    # Остановка event loop
    tasks = [t for t in asyncio.all_tasks(loop) if t is not asyncio.current_task()]
    for task in tasks:
        task.cancel()

    await asyncio.gather(*tasks, return_exceptions=True)
    loop.stop()


async def main():
    """Основная функция"""
    # Инициализация Redis
    redis_client = redis.Redis(
        host=config.REDIS_HOST,
        port=config.REDIS_PORT,
        db=config.REDIS_DB,
        decode_responses=False,
    )

    # Инициализация менеджера
    manager = MultiSymbolManager()

    # Настройка обработки сигналов
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig, lambda s=sig: asyncio.create_task(shutdown(manager, loop))
        )

    app_logger.info("🚀 Multi-Symbol Zone Analyzer starting...")
    app_logger.info(f"Symbols: {len(config.symbols)}")
    app_logger.info(f"Timeframes: {config.timeframes}")

    try:
        # Запуск менеджера
        await manager.start(redis_client)
    except KeyboardInterrupt:
        app_logger.info("Keyboard interrupt received")
    except Exception as e:
        app_logger.error(f"Fatal error: {e}")
    finally:
        app_logger.info("Analyzer stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nGoodbye!")
        sys.exit(0)
