from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import stats
from app.config import Settings
from app.db import BetsDB

STATIC_DIR = Path(__file__).parent / "static"


def create_app(db: BetsDB, settings: Settings) -> FastAPI:
    app = FastAPI(title="OKX Options Bot")
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
            "by_symbol": {
                symbol: {
                    "bets": ss.bets,
                    "wins": ss.wins,
                    "losses": ss.losses,
                    "pushes": ss.pushes,
                    "pnl_usd": ss.pnl_usd,
                    "win_rate": ss.win_rate,
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

    return app
