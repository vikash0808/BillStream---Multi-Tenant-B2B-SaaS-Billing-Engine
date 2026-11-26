"""Usage-based billing and itemized invoice calculation engine."""

from datetime import datetime, timezone
from typing import Any, Dict

from billstream.config import get_plan


def current_billing_period() -> str:
    """Return the active UTC billing period as YYYY-MM."""
    return datetime.now(timezone.utc).strftime("%Y-%m")


def calculate_invoice(
    tenant: Dict[str, Any],
    total_units: int,
    billing_period: str,
) -> Dict[str, Any]:
    """Compute itemized subscription base fee, overage units, and total due."""
    plan = get_plan(tenant["plan"])
    included = int(plan["included_units"])
    overage_units = max(0, int(total_units) - included)
    base_fee = float(plan["monthly_fee_usd"])
    overage_rate = float(plan["overage_rate_per_unit"])
    overage_fee = round(overage_units * overage_rate, 4)
    total_due = round(base_fee + overage_fee, 2)

    return {
        "tenant_id": tenant["id"],
        "tenant_name": tenant["name"],
        "plan": tenant["plan"],
        "billing_period": billing_period,
        "total_units": int(total_units),
        "included_units": included,
        "overage_units": overage_units,
        "base_fee_usd": base_fee,
        "overage_rate_per_unit": overage_rate,
        "overage_fee_usd": round(overage_fee, 2),
        "total_due_usd": total_due,
    }
