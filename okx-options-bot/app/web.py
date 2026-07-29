from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app import stats
from app.config import Settings
from app.db import BetsDB
from app.okx_client import OKXClient

log = logging.getLogger("okx_options_bot.web")

STATIC_DIR = Path(__file__).parent / "static"


class NoCacheMiddleware(BaseHTTPMiddleware):
    """Forces browsers/CDNs to revalidate on every request instead of
    serving a stale cached copy of the dashboard's HTML/JS/CSS."""

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response


def create_app(db: BetsDB, settings: Settings, client: OKXClient | None = None) -> FastAPI:
    app = FastAPI(title="OKX Options Bot")
    app.add_middleware(NoCacheMiddleware)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/summary")
    def summary() -> dict:
        closed = [dict(row) for row in db.closed_bets_chronological()]
        s = stats.compute_summary(closed, settings.starting_bankroll)
        return {
            "starting_bankroll": s.starting_bankroll,
            "balance": s.balance,
            "total_bets": s.total_bets,
            "wins": s.wins,
            "losses": s.losses,
            "pushes": s.pushes,
            "win_rate": s.win_rate,
            "total_pnl": s.total_pnl,
            "current_streak": s.current_streak,
            "current_streak_type": s.current_streak_type,
            "max_drawdown": s.max_drawdown,
            "stake_usd": settings.stake_usd,
            "bias_threshold": settings.bias_threshold,
            "by_symbol": {
                symbol: {
                    "bets": ss.bets,
                    "wins": ss.wins,
                    "losses": ss.losses,
                    "pushes": ss.pushes,
                    "pnl_usd": ss.pnl_usd,
                    "win_rate": ss.win_rate,
                    "stake_usd": settings.stake_for(symbol),
                }
                for symbol, ss in s.by_symbol.items()
            },
        }

    @app.get("/api/bets")
    def bets(limit: int = 100, symbol: str | None = None) -> list[dict]:
        rows = db.list_bets(limit=limit, symbol=symbol)
        return [dict(row) for row in rows]

    @app.get("/api/equity-curve")
    def equity_curve(symbol: str | None = None) -> list[dict]:
        closed = [dict(row) for row in db.closed_bets_chronological(symbol=symbol)]
        return stats.equity_curve(closed, settings.starting_bankroll)

    @app.get("/api/activity")
    def activity(limit: int = 50) -> list[dict]:
        rows = db.list_activity(limit=limit)
        return [dict(row) for row in rows]

    @app.get("/api/okx-balance")
    def okx_balance() -> dict:
        if client is None or not client.authenticated:
            return {"available": False, "reason": "OKX API credentials not configured"}
        try:
            balance = client.get_balance(ccy="USDT")
        except Exception:
            log.exception("Failed to fetch OKX account balance")
            return {"available": False, "reason": "Failed to reach OKX"}
        if balance is None:
            return {"available": False, "reason": "Empty response from OKX"}
        usdt = next((d for d in balance.get("details", []) if d.get("ccy") == "USDT"), None)
        if usdt is None:
            return {"available": False, "reason": "No USDT balance on this account"}
        return {
            "available": True,
            "ccy": "USDT",
            "avail_bal": float(usdt.get("availBal") or 0),
            "eq": float(usdt.get("eq") or 0),
            "demo": client.demo,
        }

    @app.get("/api/settings")
    def get_settings() -> dict:
        return {
            "symbols": settings.symbol_list,
            "candle_bar": settings.candle_bar,
            "candle_limit": settings.candle_limit,
            "poll_interval_seconds": settings.poll_interval_seconds,
            "bias_threshold": settings.bias_threshold,
            "stake_usd": settings.stake_usd,
            "stake_overrides": settings.stake_overrides,
            "starting_bankroll": settings.starting_bankroll,
            "okx_demo": settings.okx_demo,
            "okx_td_mode": settings.okx_td_mode,
            "okx_authenticated": client.authenticated if client else False,
        }

    return app
