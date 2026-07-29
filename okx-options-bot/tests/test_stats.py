import pytest

from app import stats


def bet(symbol, result, pnl, closed_at="t"):
    return {"symbol": symbol, "result": result, "pnl_usd": pnl, "closed_at": closed_at}


def test_compute_summary_empty():
    s = stats.compute_summary([], starting_bankroll=1000.0)
    assert s.total_bets == 0
    assert s.win_rate is None
    assert s.balance == 1000.0
    assert s.max_drawdown == 0.0
    assert s.current_streak == 0
    assert s.by_symbol == {}


def test_compute_summary_counts_and_pnl():
    bets = [
        bet("BTC", "WIN", 2.0),
        bet("BTC", "LOSS", -5.0),
        bet("ETH", "WIN", 3.0),
        bet("ETH", "PUSH", 0.0),
    ]
    s = stats.compute_summary(bets, starting_bankroll=100.0)
    assert s.total_bets == 4
    assert s.wins == 2
    assert s.losses == 1
    assert s.pushes == 1
    assert s.total_pnl == 0.0
    assert s.balance == 100.0
    assert s.win_rate == pytest.approx(2 / 3 * 100)
    assert s.by_symbol["BTC"].wins == 1
    assert s.by_symbol["BTC"].losses == 1
    assert s.by_symbol["BTC"].pnl_usd == -3.0
    assert s.by_symbol["ETH"].pnl_usd == 3.0


def test_compute_summary_streak_tracks_consecutive_results():
    bets = [
        bet("BTC", "WIN", 1.0),
        bet("BTC", "WIN", 1.0),
        bet("BTC", "LOSS", -1.0),
    ]
    s = stats.compute_summary(bets, starting_bankroll=100.0)
    assert s.current_streak == 1
    assert s.current_streak_type == "LOSS"


def test_compute_summary_streak_ignores_push():
    bets = [
        bet("BTC", "WIN", 1.0),
        bet("BTC", "PUSH", 0.0),
        bet("BTC", "WIN", 1.0),
    ]
    s = stats.compute_summary(bets, starting_bankroll=100.0)
    assert s.current_streak == 2
    assert s.current_streak_type == "WIN"


def test_compute_summary_max_drawdown():
    bets = [
        bet("BTC", "WIN", 10.0),  # balance 110, peak 110
        bet("BTC", "LOSS", -20.0),  # balance 90, dd = 20
        bet("BTC", "WIN", 5.0),  # balance 95
    ]
    s = stats.compute_summary(bets, starting_bankroll=100.0)
    assert s.max_drawdown == 20.0
    assert s.balance == 95.0


def test_equity_curve_starts_at_bankroll_and_accumulates():
    bets = [bet("BTC", "WIN", 5.0, closed_at="t1"), bet("BTC", "LOSS", -2.0, closed_at="t2")]
    curve = stats.equity_curve(bets, starting_bankroll=100.0)
    assert curve[0] == {"ts": None, "balance": 100.0}
    assert curve[1] == {"ts": "t1", "balance": 105.0}
    assert curve[2] == {"ts": "t2", "balance": 103.0}
