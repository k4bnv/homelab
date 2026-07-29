from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SymbolStats:
    bets: int = 0
    wins: int = 0
    losses: int = 0
    pushes: int = 0
    pnl_usd: float = 0.0

    @property
    def win_rate(self) -> float | None:
        decided = self.wins + self.losses
        return (self.wins / decided * 100) if decided else None


@dataclass
class Summary:
    starting_bankroll: float
    balance: float
    total_bets: int
    wins: int
    losses: int
    pushes: int
    win_rate: float | None
    total_pnl: float
    current_streak: int
    current_streak_type: str | None
    max_drawdown: float
    by_symbol: dict[str, SymbolStats] = field(default_factory=dict)


def compute_summary(closed_bets: list[dict], starting_bankroll: float) -> Summary:
    """`closed_bets` must be in chronological order (oldest first)."""
    by_symbol: dict[str, SymbolStats] = {}
    wins = losses = pushes = 0
    total_pnl = 0.0
    balance = starting_bankroll
    peak = balance
    max_dd = 0.0
    streak = 0
    streak_type: str | None = None

    for bet in closed_bets:
        symbol = bet["symbol"]
        result = bet["result"]
        pnl = bet["pnl_usd"] or 0.0

        symbol_stats = by_symbol.setdefault(symbol, SymbolStats())
        symbol_stats.bets += 1
        symbol_stats.pnl_usd += pnl

        if result == "WIN":
            wins += 1
            symbol_stats.wins += 1
        elif result == "LOSS":
            losses += 1
            symbol_stats.losses += 1
        else:
            pushes += 1
            symbol_stats.pushes += 1

        total_pnl += pnl
        balance += pnl
        peak = max(peak, balance)
        max_dd = max(max_dd, peak - balance)

        if result in ("WIN", "LOSS"):
            streak = streak + 1 if result == streak_type else 1
            streak_type = result

    decided = wins + losses
    win_rate = (wins / decided * 100) if decided else None

    return Summary(
        starting_bankroll=starting_bankroll,
        balance=balance,
        total_bets=len(closed_bets),
        wins=wins,
        losses=losses,
        pushes=pushes,
        win_rate=win_rate,
        total_pnl=total_pnl,
        current_streak=streak,
        current_streak_type=streak_type,
        max_drawdown=max_dd,
        by_symbol=by_symbol,
    )


def equity_curve(closed_bets: list[dict], starting_bankroll: float) -> list[dict]:
    """`closed_bets` must be in chronological order (oldest first)."""
    balance = starting_bankroll
    curve = [{"ts": None, "balance": balance}]
    for bet in closed_bets:
        balance += bet["pnl_usd"] or 0.0
        curve.append({"ts": bet["closed_at"], "balance": balance})
    return curve
