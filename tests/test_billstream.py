from pathlib import Path
import tempfile
import unittest

from app import create_app


class BillStreamTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        db_file = str(Path(self.tmp_dir.name) / "test_billstream.db")
        self.app = create_app(db_path=db_file)
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp_dir.cleanup()

    def _create_tenant(self, name="Acme Corp", plan="pro", rate_limit_per_min=None):
        payload = {"name": name, "plan": plan}
        if rate_limit_per_min is not None:
            payload["rate_limit_per_min"] = rate_limit_per_min
        resp = self.client.post("/api/v1/tenants", json=payload)
        self.assertEqual(resp.status_code, 201)
        return resp.get_json()

    def test_health_and_plans_endpoints(self):
        health = self.client.get("/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.get_json()["status"], "ok")

        plans = self.client.get("/api/v1/plans")
        self.assertEqual(plans.status_code, 200)
        self.assertIn("pro", plans.get_json()["plans"])

    def test_tenant_creation_hides_raw_api_key_in_listings(self):
        created = self._create_tenant("Alpha AI", "pro")
        raw_key = created["api_key"]
        self.assertTrue(raw_key.startswith("bs_live_"))

        listed = self.client.get("/api/v1/tenants").get_json()["tenants"]
        self.assertEqual(len(listed), 1)
        self.assertNotIn("api_key", listed[0])
        self.assertNotIn("api_key_hash", listed[0])
        self.assertEqual(listed[0]["api_key_prefix"], raw_key[:14])

    def test_rejects_missing_or_invalid_api_key(self):
        self.assertEqual(self.client.get("/api/v1/usage/summary").status_code, 401)
        self.assertEqual(
            self.client.get("/api/v1/usage/summary", headers={"X-API-Key": "bs_live_bad"}).status_code,
            401,
        )

    def test_multi_tenant_usage_and_invoice_isolation(self):
        tenant_a = self._create_tenant("Tenant A", "pro")
        tenant_b = self._create_tenant("Tenant B", "enterprise")

        resp = self.client.post(
            "/api/v1/usage",
            headers={"X-API-Key": tenant_a["api_key"]},
            json={"endpoint": "/v1/predict", "units": 250, "billing_period": "2026-11"},
        )
        self.assertEqual(resp.status_code, 201)

        summary_a = self.client.get(
            "/api/v1/usage/summary?billing_period=2026-11",
            headers={"X-API-Key": tenant_a["api_key"]},
        ).get_json()
        summary_b = self.client.get(
            "/api/v1/usage/summary?billing_period=2026-11",
            headers={"X-API-Key": tenant_b["api_key"]},
        ).get_json()

        self.assertEqual(summary_a["total_units"], 250)
        self.assertEqual(summary_b["total_units"], 0)

    def test_sliding_window_rate_limit_enforces_429(self):
        tenant = self._create_tenant("RateLimited Co", "pro", rate_limit_per_min=2)
        headers = {"X-API-Key": tenant["api_key"]}

        r1 = self.client.post("/api/v1/usage", headers=headers, json={"endpoint": "/ping", "units": 1})
        r2 = self.client.post("/api/v1/usage", headers=headers, json={"endpoint": "/ping", "units": 1})
        r3 = self.client.post("/api/v1/usage", headers=headers, json={"endpoint": "/ping", "units": 1})

        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r1.headers["X-RateLimit-Remaining"], "1")
        self.assertEqual(r2.status_code, 201)
        self.assertEqual(r2.headers["X-RateLimit-Remaining"], "0")
        self.assertEqual(r3.status_code, 429)
        self.assertIn("Retry-After", r3.headers)

    def test_free_plan_enforces_hard_monthly_quota(self):
        tenant = self._create_tenant("Starter Co", "free")
        headers = {"X-API-Key": tenant["api_key"]}

        ok = self.client.post(
            "/api/v1/usage",
            headers=headers,
            json={"endpoint": "/search", "units": 1000, "billing_period": "2026-11"},
        )
        self.assertEqual(ok.status_code, 201)

        blocked = self.client.post(
            "/api/v1/usage",
            headers=headers,
            json={"endpoint": "/search", "units": 1, "billing_period": "2026-11"},
        )
        self.assertEqual(blocked.status_code, 402)

    def test_pro_plan_overage_invoice_calculation(self):
        tenant = self._create_tenant("Growth SaaS", "pro")
        headers = {"X-API-Key": tenant["api_key"]}

        self.client.post(
            "/api/v1/usage",
            headers=headers,
            json={"endpoint": "/inference", "units": 12000, "billing_period": "2026-11"},
        )

        inv_resp = self.client.post(
            "/api/v1/invoices/generate",
            headers=headers,
            json={"billing_period": "2026-11"},
        )
        self.assertEqual(inv_resp.status_code, 201)
        invoice = inv_resp.get_json()["invoice"]
        self.assertEqual(invoice["overage_units"], 2000)
        self.assertEqual(invoice["base_fee_usd"], 49.0)
        self.assertEqual(invoice["overage_fee_usd"], 10.0)
        self.assertEqual(invoice["total_due_usd"], 59.0)

        listed = self.client.get("/api/v1/invoices", headers=headers).get_json()["invoices"]
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["id"], invoice["id"])

    def test_validation_errors_on_bad_inputs(self):
        self.assertEqual(self.client.post("/api/v1/tenants", json={"name": ""}).status_code, 400)
        self.assertEqual(
            self.client.post("/api/v1/tenants", json={"name": "Bad", "plan": "platinum"}).status_code,
            400,
        )
        tenant = self._create_tenant("Valid Co", "pro")
        self.assertEqual(
            self.client.post(
                "/api/v1/usage",
                headers={"X-API-Key": tenant["api_key"]},
                json={"units": -5},
            ).status_code,
            400,
        )


if __name__ == "__main__":
    unittest.main()
