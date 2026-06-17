"""
Classic binary-outcome Kelly criterion sizing for Polymarket YES/NO shares.
Replaces risk.py::kelly_position_size's leveraged-perp formula.
"""


def kelly_fraction_full(model_prob: float, market_price: float, side: str) -> float:
    """
    BUY_YES: b = (1-price)/price, p = model_prob, q = 1-p.
    BUY_NO:  b = price/(1-price), p = 1-model_prob, q = model_prob.
    Returns max(0, (b*p - q) / b) — clamped at 0 (never recommends negative sizing).
    """
    price = max(min(market_price, 0.999), 0.001)  # avoid division by zero at the edges

    if side == "BUY_YES":
        b = (1 - price) / price
        p = model_prob
        q = 1 - p
    elif side == "BUY_NO":
        b = price / (1 - price)
        p = 1 - model_prob
        q = model_prob
    else:
        return 0.0

    if b <= 0:
        return 0.0

    f = (b * p - q) / b
    return max(0.0, f)


def kelly_stake(full_kelly: float, kelly_multiplier: float, equity: float, single_cap: float) -> float:
    """stake = min(equity * full_kelly * kelly_multiplier, single_cap).
    kelly_multiplier e.g. 0.25 = quarter-Kelly (variance reduction vs. full Kelly)."""
    raw_stake = equity * full_kelly * kelly_multiplier
    return max(0.0, min(raw_stake, single_cap))
