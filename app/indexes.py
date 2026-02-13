"""Database index definitions. Run during app startup to ensure indexes exist."""
from app.database import get_collection
from app.logger import logger


async def ensure_indexes():
    """Create all required indexes. Safe to call multiple times (idempotent)."""
    try:
        # Users
        users = await get_collection("users")
        await users.create_index("username", unique=True)
        await users.create_index("email", unique=True)

        # Companies
        companies = await get_collection("companies")
        await companies.create_index("created_by")

        # Parties (global — not scoped by company/FY)
        parties = await get_collection("parties")
        await parties.create_index("party_type")
        await parties.create_index("name")

        # Purchase challans
        challans = await get_collection("purchase_challans")
        await challans.create_index([("company_id", 1), ("financial_year", 1)])
        await challans.create_index([("company_id", 1), ("financial_year", 1), ("challan_no", 1)], unique=True)
        await challans.create_index([("company_id", 1), ("supplier_id", 1)])
        await challans.create_index("challan_date")

        # Sales invoices
        invoices = await get_collection("sales_invoices")
        await invoices.create_index([("company_id", 1), ("financial_year", 1)])
        await invoices.create_index([("company_id", 1), ("financial_year", 1), ("invoice_no", 1)], unique=True)
        await invoices.create_index([("company_id", 1), ("customer_id", 1)])
        await invoices.create_index("invoice_date")

        # Payments — critical for the aggregation lookups
        payments = await get_collection("payments")
        await payments.create_index([("company_id", 1), ("financial_year", 1)])
        await payments.create_index("invoices.invoice_id")
        await payments.create_index("invoices.challan_id")
        await payments.create_index([("company_id", 1), ("party_id", 1)])
        await payments.create_index([("company_id", 1), ("supplier_id", 1)])

        # Inventory transfers
        transfers = await get_collection("inventory_transfers")
        await transfers.create_index([("company_id", 1), ("financial_year", 1)])
        await transfers.create_index("source_challan_id")

        # Bank accounts
        bank_accounts = await get_collection("bank_accounts")
        await bank_accounts.create_index("company_id")

        # Bank transactions
        bank_txns = await get_collection("bank_transactions")
        await bank_txns.create_index([("company_id", 1), ("bank_account_id", 1)])
        await bank_txns.create_index("reference_id")

        # Qualities (global — not scoped by company/FY)
        qualities = await get_collection("qualities")
        await qualities.create_index("name", unique=True)

        # Audit logs
        audit = await get_collection("audit_logs")
        await audit.create_index([("company_id", 1), ("timestamp", -1)])
        await audit.create_index("entity_type")

        # Counters (for atomic sequence generation)
        counters = await get_collection("counters")
        await counters.create_index([("company_id", 1), ("prefix", 1)], unique=True)

        logger.info("Database indexes ensured successfully")
    except Exception as e:
        logger.error(f"Error creating indexes: {e}")
        raise
