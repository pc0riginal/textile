"""Centralized payment calculation logic to eliminate N+1 queries and code duplication."""
import re
from datetime import datetime
from typing import List, Dict, Any, Optional
from bson import ObjectId
from app.database import get_collection, get_database


async def calculate_invoice_payments_bulk(invoice_ids: List[ObjectId]) -> Dict[ObjectId, float]:
    """Calculate total paid for multiple invoices in a single aggregation query.
    
    Returns dict mapping invoice_id -> total_paid amount.
    """
    if not invoice_ids:
        return {}

    payments_collection = await get_collection("payments")
    pipeline = [
        {"$match": {"invoices.invoice_id": {"$in": invoice_ids}}},
        {"$unwind": "$invoices"},
        {"$match": {"invoices.invoice_id": {"$in": invoice_ids}}},
        {"$group": {
            "_id": "$invoices.invoice_id",
            "total_paid": {"$sum": "$invoices.amount"}
        }}
    ]
    results = await payments_collection.aggregate(pipeline).to_list(None)
    return {r["_id"]: r["total_paid"] for r in results}


async def calculate_challan_payments_bulk(challan_ids: List[ObjectId]) -> Dict[ObjectId, float]:
    """Calculate total paid for multiple challans in a single aggregation query.
    
    Returns dict mapping challan_id -> total_paid amount.
    """
    if not challan_ids:
        return {}

    payments_collection = await get_collection("payments")
    pipeline = [
        {"$match": {"invoices.challan_id": {"$in": challan_ids}}},
        {"$unwind": "$invoices"},
        {"$match": {"invoices.challan_id": {"$in": challan_ids}}},
        {"$group": {
            "_id": "$invoices.challan_id",
            "total_paid": {"$sum": "$invoices.amount"}
        }}
    ]
    results = await payments_collection.aggregate(pipeline).to_list(None)
    return {r["_id"]: r["total_paid"] for r in results}


async def calculate_single_invoice_paid(invoice_id: ObjectId) -> float:
    """Calculate total paid for a single invoice."""
    result = await calculate_invoice_payments_bulk([invoice_id])
    return result.get(invoice_id, 0.0)


async def calculate_single_challan_paid(challan_id: ObjectId) -> float:
    """Calculate total paid for a single challan."""
    result = await calculate_challan_payments_bulk([challan_id])
    return result.get(challan_id, 0.0)


def determine_invoice_payment_status(total_amount: float, total_paid: float) -> str:
    """Determine payment status based on amounts."""
    if total_paid >= total_amount - 0.01:  # Allow small rounding
        return "paid"
    elif total_paid > 0:
        return "partial"
    return "unpaid"


def determine_challan_payment_status(total_amount: float, total_paid: float) -> Optional[str]:
    """Determine challan payment status."""
    if total_paid >= total_amount:
        return "completed"
    elif total_paid > 0:
        return "partial"
    return None


def calculate_interest(total_amount: float, total_paid: float, due_date: Optional[datetime],
                       interest_rate: float, as_of: Optional[datetime] = None) -> float:
    """Calculate interest on overdue amount."""
    if not due_date or interest_rate <= 0:
        return 0.0
    now = as_of or datetime.utcnow()
    if now <= due_date:
        return 0.0
    overdue_days = (now - due_date).days
    balance = total_amount - total_paid
    if balance <= 0:
        return 0.0
    return (balance * interest_rate * overdue_days) / (365 * 100)


async def enrich_invoices_with_payments(invoices: List[dict]) -> List[dict]:
    """Add total_paid, outstanding, and interest_amount to a list of invoices."""
    if not invoices:
        return invoices

    invoice_ids = [inv["_id"] for inv in invoices]
    paid_map = await calculate_invoice_payments_bulk(invoice_ids)
    now = datetime.utcnow()

    for inv in invoices:
        total_paid = paid_map.get(inv["_id"], 0.0)
        inv["total_paid"] = total_paid
        inv["outstanding"] = inv["total_amount"] - total_paid
        inv["interest_amount"] = calculate_interest(
            inv["total_amount"], total_paid,
            inv.get("due_date"), inv.get("interest_rate", 0), now
        )
    return invoices


async def enrich_challans_with_payments(challans: List[dict]) -> List[dict]:
    """Add total_paid and outstanding to a list of challans."""
    if not challans:
        return challans

    challan_ids = [c["_id"] for c in challans]
    paid_map = await calculate_challan_payments_bulk(challan_ids)

    for c in challans:
        total_paid = paid_map.get(c["_id"], 0.0)
        c["total_paid"] = total_paid
        c["outstanding"] = c.get("total_amount", 0) - total_paid
    return challans


def escape_regex(user_input: str) -> str:
    """Escape user input for safe use in MongoDB $regex queries."""
    return re.escape(user_input)


async def generate_sequence_number(company_id, prefix: str, collection_name: str = "counters") -> str:
    """Atomically generate the next sequence number for a given prefix + company.
    
    Uses a dedicated counters collection with findAndModify for atomicity.
    """
    counters = await get_collection(collection_name)
    result = await counters.find_one_and_update(
        {"company_id": ObjectId(company_id), "prefix": prefix},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True  # return the updated document
    )
    seq = result["seq"]
    return f"{prefix}{seq:04d}"
