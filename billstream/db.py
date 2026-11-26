"""SQLite persistence layer for tenants, metered usage events, and invoices."""

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any, Dict, Iterator, List, Optional
import uuid


class BillStreamDB:
    def __init__(self, db_path: str = "billstream.db"):
        self.db_path = db_path
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS tenants (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    plan TEXT NOT NULL,
                    api_key_hash TEXT NOT NULL UNIQUE,
                    api_key_prefix TEXT NOT NULL,
                    rate_limit_override INTEGER,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS usage_events (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    endpoint TEXT NOT NULL,
                    units INTEGER NOT NULL,
                    billing_period TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
                );

                CREATE INDEX IF NOT EXISTS idx_usage_tenant_period
                    ON usage_events (tenant_id, billing_period);

                CREATE TABLE IF NOT EXISTS invoices (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    billing_period TEXT NOT NULL,
                    plan TEXT NOT NULL,
                    total_units INTEGER NOT NULL,
                    included_units INTEGER NOT NULL,
                    overage_units INTEGER NOT NULL,
                    base_fee_usd REAL NOT NULL,
                    overage_fee_usd REAL NOT NULL,
                    total_due_usd REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
                );

                CREATE INDEX IF NOT EXISTS idx_invoices_tenant
                    ON invoices (tenant_id, billing_period);
                """
            )

    def create_tenant(
        self,
        name: str,
        plan: str,
        api_key_hash: str,
        api_key_prefix: str,
        rate_limit_override: Optional[int] = None,
    ) -> Dict[str, Any]:
        tenant_id = f"ten_{uuid.uuid4().hex[:12]}"
        created_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO tenants (id, name, plan, api_key_hash, api_key_prefix, rate_limit_override, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (tenant_id, name, plan, api_key_hash, api_key_prefix, rate_limit_override, created_at),
            )
        return {
            "id": tenant_id,
            "name": name,
            "plan": plan,
            "api_key_prefix": api_key_prefix,
            "rate_limit_override": rate_limit_override,
            "created_at": created_at,
        }

    def list_tenants(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, name, plan, api_key_prefix, rate_limit_override, created_at
                FROM tenants
                ORDER BY created_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_tenant_by_key_hash(self, api_key_hash: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, name, plan, api_key_prefix, rate_limit_override, created_at
                FROM tenants
                WHERE api_key_hash = ?
                """,
                (api_key_hash,),
            ).fetchone()
        return dict(row) if row else None

    def record_usage(
        self,
        tenant_id: str,
        endpoint: str,
        units: int,
        billing_period: str,
    ) -> Dict[str, Any]:
        event_id = f"evt_{uuid.uuid4().hex[:12]}"
        created_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO usage_events (id, tenant_id, endpoint, units, billing_period, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (event_id, tenant_id, endpoint, units, billing_period, created_at),
            )
        return {
            "id": event_id,
            "tenant_id": tenant_id,
            "endpoint": endpoint,
            "units": units,
            "billing_period": billing_period,
            "created_at": created_at,
        }

    def get_total_units(self, tenant_id: str, billing_period: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(units), 0) AS total
                FROM usage_events
                WHERE tenant_id = ? AND billing_period = ?
                """,
                (tenant_id, billing_period),
            ).fetchone()
        return int(row["total"]) if row else 0

    def get_usage_by_endpoint(self, tenant_id: str, billing_period: str) -> Dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT endpoint, SUM(units) AS units
                FROM usage_events
                WHERE tenant_id = ? AND billing_period = ?
                GROUP BY endpoint
                ORDER BY units DESC
                """,
                (tenant_id, billing_period),
            ).fetchall()
        return {row["endpoint"]: int(row["units"]) for row in rows}

    def save_invoice(self, invoice_data: Dict[str, Any]) -> Dict[str, Any]:
        invoice_id = f"inv_{uuid.uuid4().hex[:12]}"
        created_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO invoices (
                    id, tenant_id, billing_period, plan,
                    total_units, included_units, overage_units,
                    base_fee_usd, overage_fee_usd, total_due_usd, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    invoice_id,
                    invoice_data["tenant_id"],
                    invoice_data["billing_period"],
                    invoice_data["plan"],
                    invoice_data["total_units"],
                    invoice_data["included_units"],
                    invoice_data["overage_units"],
                    invoice_data["base_fee_usd"],
                    invoice_data["overage_fee_usd"],
                    invoice_data["total_due_usd"],
                    created_at,
                ),
            )
        return {"id": invoice_id, "created_at": created_at, **invoice_data}

    def list_invoices(self, tenant_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, tenant_id, billing_period, plan,
                       total_units, included_units, overage_units,
                       base_fee_usd, overage_fee_usd, total_due_usd, created_at
                FROM invoices
                WHERE tenant_id = ?
                ORDER BY created_at DESC
                """,
                (tenant_id,),
            ).fetchall()
        return [dict(row) for row in rows]
