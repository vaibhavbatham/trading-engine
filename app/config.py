import os
from typing import List, Optional, Union
from pydantic import model_validator, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Twelve Data & Market Data
    TWELVE_DATA_API_KEY: Optional[str] = None
    MARKET_DATA_MODE: str = "simulation"  # "live" | "simulation" | "replay"
    MARKET_DATA_QUEUE_SIZE: int = 10000
    SYMBOLS: Union[List[str], str] = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META"]

    # Database
    DATABASE_URL: str = "sqlite:///./trading.db"

    # Built-in Assistant (ChartBot)
    BOT_NAME: str = "ChartBot"
    BOT_VERSION: str = "1.0"
    # Deprecated external AI fields (optional / legacy)
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    CLAUDE_MODEL: Optional[str] = None

    # Server Settings
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Market Simulation & Feed
    TICK_INTERVAL_SECONDS: float = 1.0
    TICK_VOLATILITY: float = 0.001
    BATCH_INSERT_SIZE: int = 10

    # Portfolio & Execution
    INITIAL_CASH: float = 100000.0
    POSITION_SIZE_CASH_PCT: float = 0.10
    MAX_POSITION_EQUITY_PCT: float = 0.25
    SLIPPAGE_PCT: float = 0.0005
    COMMISSION_FLAT: float = 1.00

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @field_validator("SYMBOLS", mode="after")
    @classmethod
    def parse_symbols(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            return [s.strip().upper() for s in v.split(",") if s.strip()]
        return [s.upper() for s in v]

    @model_validator(mode="after")
    def validate_market_mode_and_keys(self) -> "Settings":
        mode = self.MARKET_DATA_MODE.lower()
        if mode not in ("live", "simulation", "replay"):
            raise ValueError(
                f"Invalid MARKET_DATA_MODE '{self.MARKET_DATA_MODE}'. "
                f"Supported modes are: 'live', 'simulation', 'replay'."
            )
        self.MARKET_DATA_MODE = mode

        # Strict validation for live mode: NEVER silently fall back
        if self.MARKET_DATA_MODE == "live":
            if not self.TWELVE_DATA_API_KEY or not self.TWELVE_DATA_API_KEY.strip():
                raise ValueError(
                    "MARKET_DATA_MODE is configured as 'live' but TWELVE_DATA_API_KEY is not set or empty. "
                    "Please configure a valid TWELVE_DATA_API_KEY in your .env file or explicitly switch to "
                    "MARKET_DATA_MODE=simulation."
                )

        return self


settings = Settings()
