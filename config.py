import sys
from loguru import logger
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    SYMBOL: str = "BTCUSDT"

    # Таймфреймы (15m - работа, 60m - уровни, 240m - глобальный тренд)
    TF_ENTRY: str = "15"
    TF_LEVEL: str = "60"
    TF_TREND: str = "240"

    ATR_PERIOD: int = 14
    CLUSTER_EPS_MULT: float = 0.35


config = Settings()

logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>",
)
