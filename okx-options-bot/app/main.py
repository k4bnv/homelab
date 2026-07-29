from __future__ import annotations

import logging
import time

from app import indicators, options_analysis
from app.config import Settings, load_settings
from app.formatting import format_message
from app.models import TechnicalSnapshot
from app.okx_client import OKXClient
from app.signal import evaluate_bias
from app.telegram_notifier import TelegramNotifier

log = logging.getLogger("okx_options_bot")


def build_technical_snapshot(client: OKXClient, symbol: str, bar: str, limit: int) -> TechnicalSnapshot:
    inst_id = f"{symbol}-USDT"
    candles = client.get_candles(inst_id, bar=bar, limit=limit)
    closes = [float(c[4]) for c in candles]

    macd_result = indicators.macd(closes)
    return TechnicalSnapshot(
        inst_id=inst_id,
        spot=closes[-1],
        rsi14=indicators.rsi(closes),
        macd=macd_result.macd if macd_result else None,
        macd_signal=macd_result.signal if macd_result else None,
        macd_histogram=macd_result.histogram if macd_result else None,
        ema9=indicators.ema(closes, 9),
        ema21=indicators.ema(closes, 21),
    )


def run_symbol(client: OKXClient, notifier: TelegramNotifier, settings: Settings, symbol: str) -> None:
    tech = build_technical_snapshot(client, symbol, settings.candle_bar, settings.candle_limit)

    uly = f"{symbol}-USD"
    opts_metrics = None
    try:
        raw_summary = client.get_opt_summary(uly)
        snapshots = options_analysis.parse_opt_summary(uly, raw_summary)
        if snapshots:
            raw_oi = client.get_open_interest(uly)
            options_analysis.attach_open_interest(snapshots, raw_oi)
            opts_metrics = options_analysis.compute_metrics(uly, snapshots, tech.spot)
    except Exception:
        log.exception("Failed to fetch/compute options metrics for %s", uly)

    bias = evaluate_bias(tech, opts_metrics)
    message = format_message(symbol, tech, opts_metrics, bias)
    notifier.send(message)
    log.info("Sent %s digest: bias=%s score=%d", symbol, bias.label, bias.score)


def seconds_until_next_run(interval_seconds: int) -> float:
    now = time.time()
    return interval_seconds - (now % interval_seconds)


def run_forever(settings: Settings) -> None:
    client = OKXClient(
        base_url=settings.okx_base_url,
        api_key=settings.okx_api_key,
        api_secret=settings.okx_api_secret,
        api_passphrase=settings.okx_api_passphrase,
    )
    notifier = TelegramNotifier(settings.telegram_bot_token, settings.telegram_chat_id)

    log.info(
        "Starting okx-options-bot for %s, interval=%ss, authenticated=%s",
        settings.symbol_list,
        settings.poll_interval_seconds,
        client.authenticated,
    )

    try:
        while True:
            sleep_for = seconds_until_next_run(settings.poll_interval_seconds)
            time.sleep(sleep_for)

            for symbol in settings.symbol_list:
                try:
                    run_symbol(client, notifier, settings, symbol)
                except Exception:
                    log.exception("Failed to process %s", symbol)
    finally:
        client.close()
        notifier.close()


def main() -> None:
    settings = load_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    run_forever(settings)


if __name__ == "__main__":
    main()
