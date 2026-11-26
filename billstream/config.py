"""Subscription plan definitions, quotas, rate limits, and overage pricing."""

from typing import Any, Dict

PLANS: Dict[str, Dict[str, Any]] = {
    "free": {
        "name": "Free",
        "monthly_fee_usd": 0.0,
        "included_units": 1000,
        "overage_rate_per_unit": 0.0,
        "rate_limit_per_min": 30,
        "allow_overage": False,
    },
    "pro": {
        "name": "Pro",
        "monthly_fee_usd": 49.0,
        "included_units": 10000,
        "overage_rate_per_unit": 0.005,
        "rate_limit_per_min": 120,
        "allow_overage": True,
    },
    "enterprise": {
        "name": "Enterprise",
        "monthly_fee_usd": 299.0,
        "included_units": 100000,
        "overage_rate_per_unit": 0.002,
        "rate_limit_per_min": 600,
        "allow_overage": True,
    },
}


def get_plan(plan_id: str) -> Dict[str, Any]:
    key = (plan_id or "").strip().lower()
    if key not in PLANS:
        raise ValueError(f"Unsupported plan '{plan_id}'. Valid plans: {', '.join(PLANS.keys())}")
    return PLANS[key]
