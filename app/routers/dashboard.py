from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta
from bson import ObjectId

from app import TEMPLATES_DIR
from app.dependencies import get_current_user, get_current_company, get_company_filter
from app.database import get_collection

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)

@router.get("/dashboard")
async def dashboard(
    request: Request,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company)
):
    # Get user's companies for company switcher
    companies_collection = await get_collection("companies")
    user_companies = await companies_collection.find(
        {"_id": {"$in": [ObjectId(cid) for cid in current_user.get("companies", [])]}}
    ).to_list(None)
    # Get dashboard metrics
    today = datetime.now().date()
    start_of_month = datetime(today.year, today.month, 1)
    
    # Collections
    challans_collection = await get_collection("purchase_challans")
    invoices_collection = await get_collection("sales_invoices")
    payments_collection = await get_collection("payments")
    parties_collection = await get_collection("parties")
    
    base_filter = get_company_filter(current_company)
    
    # Today's metrics
    today_sales = await invoices_collection.aggregate([
        {"$match": {
            **base_filter,
            "invoice_date": {"$gte": datetime.combine(today, datetime.min.time())}
        }},
        {"$group": {"_id": None, "total": {"$sum": "$total_amount"}}}
    ]).to_list(1)
    
    today_purchases = await challans_collection.aggregate([
        {"$match": {
            **base_filter,
            "challan_date": {"$gte": datetime.combine(today, datetime.min.time())}
        }},
        {"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$total_amount", 0]}}}}
    ]).to_list(1)
    
    # Outstanding amounts
    total_receivables = await parties_collection.aggregate([
        {"$match": {"current_balance": {"$gt": 0}}},
        {"$group": {"_id": None, "total": {"$sum": "$current_balance"}}}
    ]).to_list(1)
    
    total_payables = await parties_collection.aggregate([
        {"$match": {"current_balance": {"$lt": 0}}},
        {"$group": {"_id": None, "total": {"$sum": {"$abs": "$current_balance"}}}}
    ]).to_list(1)
    
    # Recent transactions
    recent_invoices = await invoices_collection.find(
        base_filter,
        sort=[("created_at", -1)],
        limit=5
    ).to_list(5)
    
    recent_challans = await challans_collection.find(
        base_filter,
        sort=[("created_at", -1)],
        limit=5
    ).to_list(5)
    
    # Prepare metrics
    metrics = {
        "today_sales": today_sales[0]["total"] if today_sales else 0,
        "today_purchases": today_purchases[0]["total"] if today_purchases else 0,
        "total_receivables": total_receivables[0]["total"] if total_receivables else 0,
        "total_payables": total_payables[0]["total"] if total_payables else 0,
    }
    
    # Get financial years from current company only
    financial_years = current_company.get("financial_years", [])
    if not financial_years and current_company.get("financial_year"):
        financial_years = [current_company.get("financial_year")]
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "current_user": current_user,
        "current_company": current_company,
        "user_companies": user_companies,
        "financial_years": financial_years,
        "metrics": metrics,
        "recent_invoices": recent_invoices,
        "recent_challans": recent_challans,
        "breadcrumbs": [{"name": "Dashboard", "url": "/dashboard"}]
    })