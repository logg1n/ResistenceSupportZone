import redis.asyncio as redis
import json
from config import config


class RedisClient:
    def __init__(self):
        self.client = redis.Redis(
            host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True
        )

    async def push_candle(self, tf: str, candle: dict):
        key = f"history:{config.SYMBOL}:{tf}"
        await self.client.lpush(key, json.dumps(candle))
        await self.client.ltrim(key, 0, 500)
        await self.client.publish("candle_updates", tf)

    async def get_history(self, tf: str):
        key = f"history:{config.SYMBOL}:{tf}"
        data = await self.client.lrange(key, 0, -1)
        return [json.loads(d) for d in data[::-1]]

    async def save_signal(self, signal: dict):
        await self.client.lpush("trading_signals", json.dumps(signal))

    async def pop_signal(self):
        data = await self.client.rpop("trading_signals")
        return json.loads(data) if data else None
