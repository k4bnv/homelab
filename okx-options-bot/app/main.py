from __future__ import annotations

import logging
import threading
import time

import uvicorn

from app import bet_engine
from app.config import Settings, load_settings
from app.db import BetsDB
from app.okx_client import OKXClient
from app.web import create_app

log = logging.getLogger("okx_options_bot")


def seconds_until_next_run(interval_seconds: int) -> float:
    now = time.time()
    return interval_seconds - (now % interval_seconds)


def run_scheduler(
    db: BetsDB, client: OKXClient, settings: Settings, stop_event: threading.Event
) -> None:
    log.info(
        "Bet engine started for %s, interval=%ss, authenticated=%s",
        settings.symbol_list,
        settings.poll_interval_seconds,
        client.authenticated,
    )
    while not stop_event.is_set():
        sleep_for = seconds_until_next_run(settings.poll_interval_seconds)
        if stop_event.wait(sleep_for):
            break
        for symbol in settings.symbol_list:
            try:
                bet_engine.run_symbol(db, client, settings, symbol)
            except Exception:
                log.exception("Failed to process %s", symbol)


def main() -> None:
    settings = load_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    db = BetsDB(settings.db_path)
    client = OKXClient(
        base_url=settings.okx_base_url,
        api_key=settings.okx_api_key,
        api_secret=settings.okx_api_secret,
        api_passphrase=settings.okx_api_passphrase,
    )

    stop_event = threading.Event()
    scheduler_thread = threading.Thread(
        target=run_scheduler, args=(db, client, settings, stop_event), daemon=True
    )
    scheduler_thread.start()

    app = create_app(db, settings)
    try:
        uvicorn.run(
            app,
            host=settings.http_host,
            port=settings.http_port,
            log_level=settings.log_level.lower(),
        )
    finally:
        stop_event.set()
        client.close()
        db.close()


if __name__ == "__main__":
    main()
