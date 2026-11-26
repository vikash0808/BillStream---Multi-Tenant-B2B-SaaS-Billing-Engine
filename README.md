# 💳 BillStream — Multi-Tenant B2B SaaS Billing Engine

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-000000?style=for-the-badge&logo=flask&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white)
![Architecture](https://img.shields.io/badge/Architecture-Multi--Tenant_SaaS-2563EB?style=for-the-badge)

**BillStream** is a multi-tenant API billing and rate-limiting platform designed to manage tenant API keys, enforce per-tenant sliding-window request limits, meter real-time consumption, and generate usage-based B2B SaaS invoices.

---

## ✨ Key Features

- **Multi-Tenant Onboarding & Secure API Keys:** Provisions tenants across `free`, `pro`, and `enterprise` tiers with high-entropy keys (`bs_live_...`) stored strictly as **SHA-256 hashes** (never plaintext).
- **Per-Tenant Sliding-Window Rate Limiter:** Thread-safe rate limiter enforcing requests-per-minute caps with standard `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `Retry-After`, and HTTP `429 Too Many Requests` responses.
- **Usage Metering & Quota Enforcement:** Tracks billable API units per tenant and endpoint in SQLite; enforces hard monthly caps (`402 Payment Required`) on Free tier and metered overages on Pro/Enterprise tiers.
- **Usage-Based Invoice Engine:** Calculates itemized monthly bills (base fee + included quota + overage units × overage rate) and persists invoices per tenant with strict tenant isolation.
- **Automated Test Suite:** Verified with `unittest` covering auth, tenant isolation, rate limits, quotas, and overage billing math.

---

## 📊 Subscription Plans

| Plan | Monthly Base Fee | Included Units / Month | Overage Rate | Default Rate Limit |
| :--- | ---: | ---: | ---: | ---: |
| **Free** | $0.00 | 1,000 | Hard cap (`402`) | 30 req/min |
| **Pro** | $49.00 | 10,000 | $0.005 / unit | 120 req/min |
| **Enterprise** | $299.00 | 100,000 | $0.002 / unit | 600 req/min |

---

## 📁 Project Structure

```text
BillStream---Multi-Tenant-B2B-SaaS-Billing-Engine/
├── app.py                   # Flask REST API entry point
├── billstream/
│   ├── __init__.py
│   ├── config.py            # Subscription plans, quotas & overage pricing
│   ├── auth.py              # API key generation & SHA-256 hashing
│   ├── rate_limiter.py      # Thread-safe sliding-window rate limiter
│   ├── billing.py           # Itemized usage & overage invoice calculator
│   └── db.py                # SQLite schema & multi-tenant persistence
├── tests/
│   └── test_billstream.py   # End-to-end automated test suite
├── requirements.txt
├── .gitignore
└── README.md
```

---

## 💻 Getting Started

### 1. Clone & Install
```bash
git clone https://github.com/vikash0808/BillStream---Multi-Tenant-B2B-SaaS-Billing-Engine.git
cd BillStream---Multi-Tenant-B2B-SaaS-Billing-Engine
pip install -r requirements.txt
```

### 2. Run the API Server
```bash
python app.py
```

### 3. Try the API
```bash
# 1. Create a Pro tenant (returns your one-time X-API-Key)
curl -X POST http://127.0.0.1:5000/api/v1/tenants \
  -H "Content-Type: application/json" \
  -d '{"name": "Acme AI", "plan": "pro"}'

# 2. Record metered API usage
curl -X POST http://127.0.0.1:5000/api/v1/usage \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <YOUR_API_KEY>" \
  -d '{"endpoint": "/v1/predict", "units": 12000, "billing_period": "2026-11"}'

# 3. Generate an itemized invoice
curl -X POST http://127.0.0.1:5000/api/v1/invoices/generate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <YOUR_API_KEY>" \
  -d '{"billing_period": "2026-11"}'
```

### 4. Run Tests
```bash
python -m unittest discover -s tests -v
```

---

## 👨‍💻 Author

**Vikash Dhillan** — B.Tech Computer Science  
GitHub: [@vikash0808](https://github.com/vikash0808)
