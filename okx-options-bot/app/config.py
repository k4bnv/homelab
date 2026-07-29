from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    okx_base_url: str = "https://www.okx.com"
    okx_api_key: str = ""
    okx_api_secret: str = ""
    okx_api_passphrase: str = ""
    okx_demo: bool = True

    symbols: str = "BTC,ETH"
    candle_bar: str = "15m"
    candle_limit: int = 150
    poll_interval_seconds: int = 900

    # Minimum |bias score| required to open a bet. Score is the sum of 4
    # +-1 factors (RSI, MACD, put/call OI ratio, 25d IV skew), so valid
    # range is 1-4. Lower = more (lower-conviction) trades, higher = fewer
    # (higher-conviction) trades.
    bias_threshold: int = 1

    stake_usd: float = 5.0
    # Per-symbol overrides, e.g. "BTC:10,ETH:5,SOL:2" - falls back to
    # stake_usd for any symbol not listed here.
    stake_usd_overrides: str = ""

    starting_bankroll: float = 1000.0
    db_path: str = "./data/bets.db"

    http_host: str = "0.0.0.0"
    http_port: int = 8000

    log_level: str = "INFO"

    @property
    def symbol_list(self) -> list[str]:
        return [s.strip().upper() for s in self.symbols.split(",") if s.strip()]

    @property
    def okx_authenticated(self) -> bool:
        return bool(self.okx_api_key and self.okx_api_secret and self.okx_api_passphrase)

    @property
    def stake_overrides(self) -> dict[str, float]:
        result: dict[str, float] = {}
        for pair in self.stake_usd_overrides.split(","):
            pair = pair.strip()
            if not pair or ":" not in pair:
                continue
            symbol, _, amount = pair.partition(":")
            symbol = symbol.strip().upper()
            try:
                result[symbol] = float(amount.strip())
            except ValueError:
                continue
        return result

    def stake_for(self, symbol: str) -> float:
        return self.stake_overrides.get(symbol.upper(), self.stake_usd)


def load_settings() -> Settings:
    return Settings()
