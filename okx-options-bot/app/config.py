from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    okx_base_url: str = "https://www.okx.com"
    okx_api_key: str = ""
    okx_api_secret: str = ""
    okx_api_passphrase: str = ""

    symbols: str = "BTC,ETH"
    candle_bar: str = "15m"
    candle_limit: int = 150
    poll_interval_seconds: int = 900

    stake_usd: float = 5.0
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


def load_settings() -> Settings:
    return Settings()
