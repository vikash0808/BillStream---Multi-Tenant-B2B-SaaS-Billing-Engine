"""BillStream REST API — Multi-tenant metering, sliding-window rate limiting & billing."""

import os
from typing import Optional

from flask import Flask, jsonify, make_response, request

from billstream.auth import generate_api_key, hash_api_key, key_prefix
from billstream.billing import calculate_invoice, current_billing_period
from billstream.config import PLANS, get_plan
from billstream.db import BillStreamDB
from billstream.rate_limiter import SlidingWindowRateLimiter


def create_app(
    db_path: Optional[str] = None,
    rate_limiter: Optional[SlidingWindowRateLimiter] = None,
) -> Flask:
    app = Flask(__name__)
    resolved_db_path = db_path or os.getenv("BILLSTREAM_DB_PATH", "billstream.db")
    db = BillStreamDB(resolved_db_path)
    limiter = rate_limiter or SlidingWindowRateLimiter(window_seconds=60)

    def authenticate_tenant():
        raw_key = (request.headers.get("X-API-Key") or "").strip()
        if not raw_key:
            return None, (jsonify({"error": "Missing X-API-Key header."}), 401)
        tenant = db.get_tenant_by_key_hash(hash_api_key(raw_key))
        if not tenant:
            return None, (jsonify({"error": "Invalid API key."}), 401)
        return tenant, None

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok", "service": "BillStream"})

    @app.route("/api/v1/plans", methods=["GET"])
    def list_plans():
        return jsonify({"plans": PLANS})

    @app.route("/api/v1/tenants", methods=["POST"])
    def create_tenant():
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        plan_id = (data.get("plan") or "free").strip().lower()
        rate_limit_override = data.get("rate_limit_per_min")

        if not name:
            return jsonify({"error": "Tenant 'name' is required."}), 400
        try:
            get_plan(plan_id)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        if rate_limit_override is not None:
            if not isinstance(rate_limit_override, int) or rate_limit_override <= 0:
                return jsonify({"error": "'rate_limit_per_min' must be a positive integer."}), 400

        raw_key = generate_api_key()
        tenant = db.create_tenant(
            name=name[:80],
            plan=plan_id,
            api_key_hash=hash_api_key(raw_key),
            api_key_prefix=key_prefix(raw_key),
            rate_limit_override=rate_limit_override,
        )
        return (
            jsonify(
                {
                    "tenant": tenant,
                    "api_key": raw_key,
                    "warning": "Store this API key securely; it will not be shown again.",
                }
            ),
            201,
        )

    @app.route("/api/v1/tenants", methods=["GET"])
    def list_tenants():
        return jsonify({"tenants": db.list_tenants()})

    @app.route("/api/v1/usage", methods=["POST"])
    def record_usage():
        tenant, auth_error = authenticate_tenant()
        if auth_error:
            return auth_error

        plan = get_plan(tenant["plan"])
        limit = tenant["rate_limit_override"] or int(plan["rate_limit_per_min"])
        allowed, remaining, retry_after = limiter.check_and_consume(tenant["id"], limit)

        if not allowed:
            resp = make_response(
                jsonify(
                    {
                        "error": "Rate limit exceeded for tenant.",
                        "limit_per_min": limit,
                        "retry_after_seconds": retry_after,
                    }
                ),
                429,
            )
            resp.headers["X-RateLimit-Limit"] = str(limit)
            resp.headers["X-RateLimit-Remaining"] = "0"
            resp.headers["Retry-After"] = str(retry_after)
            return resp

        data = request.get_json(silent=True) or {}
        endpoint = (data.get("endpoint") or "/default").strip()[:120]
        units = data.get("units", 1)
        billing_period = (data.get("billing_period") or current_billing_period()).strip()

        if not isinstance(units, int) or units <= 0:
            return jsonify({"error": "'units' must be a positive integer."}), 400

        current_total = db.get_total_units(tenant["id"], billing_period)
        included = int(plan["included_units"])
        if not plan["allow_overage"] and (current_total + units) > included:
            return (
                jsonify(
                    {
                        "error": "Monthly plan quota exceeded. Upgrade plan to enable overage billing.",
                        "plan": tenant["plan"],
                        "current_units": current_total,
                        "included_units": included,
                    }
                ),
                402,
            )

        event = db.record_usage(tenant["id"], endpoint, units, billing_period)
        new_total = current_total + units

        resp = make_response(
            jsonify(
                {
                    "event": event,
                    "period_total_units": new_total,
                    "included_units": included,
                }
            ),
            201,
        )
        resp.headers["X-RateLimit-Limit"] = str(limit)
        resp.headers["X-RateLimit-Remaining"] = str(remaining)
        return resp

    @app.route("/api/v1/usage/summary", methods=["GET"])
    def usage_summary():
        tenant, auth_error = authenticate_tenant()
        if auth_error:
            return auth_error

        period = (request.args.get("billing_period") or current_billing_period()).strip()
        total_units = db.get_total_units(tenant["id"], period)
        by_endpoint = db.get_usage_by_endpoint(tenant["id"], period)
        preview = calculate_invoice(tenant, total_units, period)

        return jsonify(
            {
                "tenant_id": tenant["id"],
                "plan": tenant["plan"],
                "billing_period": period,
                "total_units": total_units,
                "by_endpoint": by_endpoint,
                "estimated_billing": preview,
            }
        )

    @app.route("/api/v1/invoices/generate", methods=["POST"])
    def generate_invoice():
        tenant, auth_error = authenticate_tenant()
        if auth_error:
            return auth_error

        data = request.get_json(silent=True) or {}
        period = (data.get("billing_period") or current_billing_period()).strip()
        total_units = db.get_total_units(tenant["id"], period)
        calc = calculate_invoice(tenant, total_units, period)
        saved = db.save_invoice(calc)
        return jsonify({"invoice": saved}), 201

    @app.route("/api/v1/invoices", methods=["GET"])
    def list_invoices():
        tenant, auth_error = authenticate_tenant()
        if auth_error:
            return auth_error
        return jsonify({"invoices": db.list_invoices(tenant["id"])})

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="127.0.0.1", port=port, debug=debug_mode)
