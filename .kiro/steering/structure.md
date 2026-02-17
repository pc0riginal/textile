# Project Structure

```
├── main.py                  # FastAPI app entry point, router registration, lifespan events, index creation
├── config.py                # Settings class (env vars via python-decouple), ALLOWED_ORIGINS, SECRET_KEY safety
├── start.py                 # Dev startup script (DB connection check + uvicorn launch)
├── requirements.txt         # Python dependencies
├── Dockerfile / docker-compose.yml
│
├── app/
│   ├── __init__.py
│   ├── database.py          # MongoDB connection (Motor), get_collection() helper
│   ├── auth.py              # JWT creation/verification, bcrypt password hashing (direct, no passlib)
│   ├── dependencies.py      # FastAPI dependency injection (auth, company, template context)
│   ├── enums.py             # String enums: PartyType, PaymentType, PaymentStatus, DocumentStatus, etc.
│   ├── indexes.py           # Database index definitions, called on startup via ensure_indexes()
│   ├── logger.py            # Rotating file logger → logs/app.log
│   ├── utils.py             # Utility functions (number_to_words for Indian numbering)
│   │
│   ├── models/              # Pydantic models (validation only, not ORM)
│   │   ├── audit.py         # AuditLog, AuditLogCreate
│   │   ├── bank.py          # BankAccount
│   │   ├── challan.py       # PurchaseChallan, ChallanItem (inventory tracking fields)
│   │   ├── company.py       # Company, Address, Contact, BankDetail
│   │   ├── party.py         # Party, PartyCreate
│   │   ├── transfer.py      # InventoryTransfer, TransferRecipient
│   │   └── user.py          # User, UserCreate, UserLogin
│   │
│   ├── routers/             # FastAPI APIRouter modules (one per domain)
│   │   ├── auth.py          # /auth — login, register, logout
│   │   ├── dashboard.py     # /dashboard — metrics, recent activity
│   │   ├── companies.py     # /companies — CRUD, company/FY switching
│   │   ├── parties.py       # /parties — CRUD, quick-add API, search (regex-escaped)
│   │   ├── purchase_invoices.py  # Purchase challans
│   │   ├── invoices.py      # /invoices — sales invoices (bulk payment enrichment)
│   │   ├── transfers.py     # /transfers — inventory transfers
│   │   ├── payments.py      # /payments — payment/receipt management (uses payment_service)
│   │   ├── banking.py       # /banking — bank accounts, passbook
│   │   ├── qualities.py     # Fabric quality master
│   │   ├── reports.py       # Report generation (bulk payment enrichment)
│   │   ├── user.py          # User profile/settings
│   │   ├── settings.py      # App settings
│   │   └── debug.py         # Debug endpoints (only loaded when DEBUG=true)
│   │
│   ├── services/            # Business logic layer
│   │   ├── audit_service.py      # Audit logging
│   │   ├── inventory_service.py  # Inventory transfer logic (with MongoDB transactions)
│   │   └── payment_service.py    # Bulk payment calculations, interest, status, atomic sequence numbers
│   │
│   ├── templates/           # Jinja2 HTML templates
│   │   ├── base.html        # Base layout
│   │   ├── components/      # Shared components (navbar, sidebar)
│   │   └── {domain}/        # Templates per domain (list, create, edit, view)
│   │
│   └── static/
│       ├── js/              # Vanilla JS (app.js, searchable-dropdown.js)
│       └── images/
```

## Architecture Patterns

- **Router → Database direct**: Routers query MongoDB collections directly via `get_collection()`. No repository layer.
- **Services for complex logic**: `inventory_service.py` (with transactions), `payment_service.py` (bulk aggregation), `audit_service.py`.
- **Dependency injection**: Auth and company context injected via FastAPI `Depends()` — see `dependencies.py`.
- **Company + FY scoping**: All queries include `company_id` and `financial_year` filters via `get_company_filter()`.
- **Template context**: `get_template_context()` dependency provides `request`, `current_user`, `current_company`, `user_companies`, `financial_years` to templates.
- **Dual endpoints per entity**: HTML form endpoints (GET/POST) for UI + JSON API endpoints (`/api/...`) for AJAX.
- **Breadcrumbs**: Each page passes a `breadcrumbs` list to the template context.
- **ObjectId handling**: MongoDB `_id` fields are converted to string `id` fields in API responses. `bson.ObjectId` used for all DB queries.
- **Timestamps**: `created_at` / `updated_at` fields use `datetime.utcnow()`.
- **Bulk payment enrichment**: Use `enrich_invoices_with_payments()` / `enrich_challans_with_payments()` from `payment_service.py` instead of per-document queries.
- **Atomic sequence numbers**: Use `generate_sequence_number()` from `payment_service.py` for TR/REC/PAY/CH numbers — uses `counters` collection with `findOneAndUpdate`.
- **MongoDB transactions**: Multi-step operations in `inventory_service.py` use `start_session()` + `start_transaction()` for atomicity.
- **Enums**: Use `app/enums.py` for party types, payment types, statuses, etc. to avoid magic strings.
