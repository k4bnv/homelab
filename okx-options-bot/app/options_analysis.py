from __future__ import annotations

from app.models import OptionSnapshot, OptionsMetrics


def _parse_inst_id(inst_id: str) -> tuple[str, float, str] | None:
    """Parses 'BTC-USD-250926-60000-C' -> (expiry, strike, opt_type)."""
    parts = inst_id.split("-")
    if len(parts) != 5:
        return None
    _, _, expiry, strike, opt_type = parts
    try:
        return expiry, float(strike), opt_type
    except ValueError:
        return None


def parse_opt_summary(uly: str, raw_items: list[dict]) -> list[OptionSnapshot]:
    snapshots = []
    for item in raw_items:
        parsed = _parse_inst_id(item["instId"])
        if parsed is None:
            continue
        expiry, strike, opt_type = parsed
        try:
            snapshots.append(
                OptionSnapshot(
                    inst_id=item["instId"],
                    uly=uly,
                    expiry=expiry,
                    strike=strike,
                    opt_type=opt_type,
                    delta_bs=float(item.get("deltaBS", 0) or 0),
                    gamma_bs=float(item.get("gammaBS", 0) or 0),
                    theta_bs=float(item.get("thetaBS", 0) or 0),
                    vega_bs=float(item.get("vegaBS", 0) or 0),
                    mark_vol=float(item.get("markVol", 0) or 0),
                )
            )
        except (TypeError, ValueError):
            continue
    return snapshots


def attach_open_interest(snapshots: list[OptionSnapshot], oi_raw: list[dict]) -> None:
    oi_by_inst = {item["instId"]: float(item.get("oi", 0) or 0) for item in oi_raw}
    for snap in snapshots:
        snap.oi = oi_by_inst.get(snap.inst_id, 0.0)


def nearest_expiry(snapshots: list[OptionSnapshot]) -> str | None:
    expiries = {s.expiry for s in snapshots}
    return min(expiries) if expiries else None


def _closest(snaps: list[OptionSnapshot], key_fn, target: float) -> OptionSnapshot | None:
    if not snaps:
        return None
    return min(snaps, key=lambda s: abs(key_fn(s) - target))


def compute_metrics(
    uly: str, snapshots: list[OptionSnapshot], spot: float
) -> OptionsMetrics | None:
    expiry = nearest_expiry(snapshots)
    if expiry is None:
        return None

    near = [s for s in snapshots if s.expiry == expiry]
    calls = [s for s in near if s.opt_type == "C"]
    puts = [s for s in near if s.opt_type == "P"]

    atm_call = _closest(calls, lambda s: s.strike, spot)
    atm_put = _closest(puts, lambda s: s.strike, spot)
    atm_vols = [s.mark_vol for s in (atm_call, atm_put) if s and s.mark_vol]
    atm_iv = sum(atm_vols) / len(atm_vols) if atm_vols else None

    call_25d = _closest(calls, lambda s: s.delta_bs, 0.25)
    put_25d = _closest(puts, lambda s: s.delta_bs, -0.25)
    iv_skew = None
    if call_25d and put_25d and call_25d.mark_vol and put_25d.mark_vol:
        iv_skew = put_25d.mark_vol - call_25d.mark_vol

    call_oi = sum(s.oi for s in calls)
    put_oi = sum(s.oi for s in puts)
    pcr = (put_oi / call_oi) if call_oi else None

    total_oi = sum(s.oi for s in near)
    if total_oi > 0:
        w_delta = sum(s.delta_bs * s.oi for s in near) / total_oi
        w_gamma = sum(s.gamma_bs * s.oi for s in near) / total_oi
        w_theta = sum(s.theta_bs * s.oi for s in near) / total_oi
        w_vega = sum(s.vega_bs * s.oi for s in near) / total_oi
    else:
        w_delta = w_gamma = w_theta = w_vega = None

    return OptionsMetrics(
        uly=uly,
        expiry=expiry,
        spot=spot,
        contracts_considered=len(near),
        atm_iv=atm_iv,
        iv_skew_25d=iv_skew,
        put_call_oi_ratio=pcr,
        oi_weighted_delta=w_delta,
        oi_weighted_gamma=w_gamma,
        oi_weighted_theta=w_theta,
        oi_weighted_vega=w_vega,
    )
