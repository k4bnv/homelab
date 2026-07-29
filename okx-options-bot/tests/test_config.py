from app.config import Settings


def test_stake_for_falls_back_to_global_default():
    settings = Settings(stake_usd=5.0, stake_usd_overrides="")
    assert settings.stake_for("BTC") == 5.0
    assert settings.stake_for("ETH") == 5.0


def test_stake_for_uses_override():
    settings = Settings(stake_usd=5.0, stake_usd_overrides="BTC:10,ETH:2.5")
    assert settings.stake_for("BTC") == 10.0
    assert settings.stake_for("ETH") == 2.5
    assert settings.stake_for("SOL") == 5.0  # not overridden


def test_stake_for_is_case_insensitive():
    settings = Settings(stake_usd=5.0, stake_usd_overrides="btc:10")
    assert settings.stake_for("BTC") == 10.0
    assert settings.stake_for("btc") == 10.0


def test_stake_overrides_ignores_malformed_entries():
    settings = Settings(stake_usd_overrides="BTC:10, garbage, ETH:notanumber, SOL:3")
    assert settings.stake_overrides == {"BTC": 10.0, "SOL": 3.0}


def test_symbol_list_parses_comma_separated():
    settings = Settings(symbols="btc, eth,sol")
    assert settings.symbol_list == ["BTC", "ETH", "SOL"]
