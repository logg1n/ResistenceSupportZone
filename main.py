import asyncio
from db_storage import RedisClient
from ta_logic import ZoneEngine
from ws_client import BybitDataStream
from config import config, logger


async def analysis_loop(db, engine):
    ps = db.client.pubsub()
    await ps.subscribe("candle_updates")
    async for msg in ps.listen():
        if msg["type"] == "message" and msg["data"] == config.TF_ENTRY:
            sig = await engine.get_signal(db)
            if sig:
                await db.save_signal(sig)


async def main():
    db = RedisClient()
    engine = ZoneEngine()
    ws = BybitDataStream(db)

    logger.info(f"Starting Multi-TF System: {config.SYMBOL}")

    # Запускаем всё в одном Event Loop
    await asyncio.gather(ws.connect(), analysis_loop(db, engine))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.warning("System stopped by user")
