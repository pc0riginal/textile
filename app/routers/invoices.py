from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, JSONResponse
from datetime import datetime
from bson import ObjectId
from typing import List

from app.dependencies import get_current_user, get_current_company, get_company_filter, get_template_context
from app.database import get_collection
from app.services.audit_service import AuditService
from app.utils import number_to_words
from app.logger import logger

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("")
async def list_invoices(
    context: dict = Depends(get_template_context)
):
    invoices_collection = await get_collection("sales_invoices")
    payments_collection = await get_collection("payments")
    
    invoices = await invoices_collection.find(
        get_company_filter(context["current_company"])
    ).sort("invoice_date", -1).to_list(None)
    
    today = datetime.utcnow()
    for inv in invoices:
        # Calculate actual paid amount
        existing_payments = await payments_collection.find({"invoices.invoice_id": inv["_id"]}).to_list(None)
        total_paid = sum(
            item["amount"] for p in existing_payments 
            for item in p.get("invoices", []) 
            if item["invoice_id"] == inv["_id"]
        )
        inv["total_paid"] = total_paid
        
        # Calculate interest if overdue
        interest = 0
        if inv.get("due_date") and inv.get("payment_status") != "paid":
            if today > inv["due_date"]:
                overdue_days = (today - inv["due_date"]).days
                balance = inv["total_amount"] - total_paid
                interest_rate = inv.get("interest_rate", 0)
                if interest_rate > 0 and balance > 0:
                    interest = (balance * interest_rate * overdue_days) / (365 * 100)
        
        inv["interest_amount"] = interest
        inv["outstanding"] = inv["total_amount"] - total_paid
    
    context.update({
        "invoices": invoices,
        "breadcrumbs": [
            {"name": "Dashboard", "url": "/dashboard"},
            {"name": "Sales Invoices", "url": "/invoices"}
        ]
    })
    return templates.TemplateResponse("invoices/list.html", context)

@router.get("/report")
async def sales_report(
    context: dict = Depends(get_template_context)
):
    from datetime import datetime, timedelta
    
    request = context["request"]
    current_company = context["current_company"]
    
    start_date = request.query_params.get('start_date')
    end_date = request.query_params.get('end_date')
    customer_id = request.query_params.get('customer_id')
    broker_id = request.query_params.get('broker_id')
    quality = request.query_params.get('quality')
    payment_filter = request.query_params.get('payment_filter', 'all')
    
    invoices_collection = await get_collection("sales_invoices")
    parties_collection = await get_collection("parties")
    qualities_collection = await get_collection("qualities")
    
    filter_query = get_company_filter(current_company)
    
    if start_date and end_date:
        filter_query["invoice_date"] = {
            "$gte": datetime.fromisoformat(start_date),
            "$lte": datetime.fromisoformat(end_date)
        }
    
    if customer_id:
        filter_query["customer_id"] = ObjectId(customer_id)
    
    if broker_id:
        filter_query["broker_id"] = ObjectId(broker_id)
    
    if quality:
        filter_query["items.quality"] = quality
    
    if payment_filter == 'dues':
        filter_query["payment_status"] = {"$in": ["unpaid", "partial"]}
    elif payment_filter == 'paid':
        filter_query["payment_status"] = "paid"
    
    invoices = await invoices_collection.find(filter_query).sort("invoice_date", -1).to_list(None)
    
    today = datetime.utcnow()
    payments_collection = await get_collection("payments")
    
    for inv in invoices:
        if inv.get("broker_id"):
            broker = await parties_collection.find_one({"_id": inv["broker_id"]})
            if broker:
                inv["broker_name"] = broker["name"]
        
        # Calculate actual paid amount from payments
        existing_payments = await payments_collection.find({"invoices.invoice_id": inv["_id"]}).to_list(None)
        total_paid = sum(
            item["amount"] for p in existing_payments 
            for item in p.get("invoices", []) 
            if item["invoice_id"] == inv["_id"]
        )
        inv["total_paid"] = total_paid
        inv["balance_amount"] = inv["total_amount"] - total_paid
        
        # Calculate interest for overdue invoices
        inv["interest_amount"] = 0
        if inv.get("due_date") and inv.get("payment_status") != "paid":
            if today > inv["due_date"]:
                overdue_days = (today - inv["due_date"]).days
                outstanding = inv["balance_amount"]
                interest_rate = inv.get("interest_rate", 0)
                if interest_rate > 0:
                    inv["interest_amount"] = (outstanding * interest_rate * overdue_days) / (365 * 100)
                inv["overdue_days"] = overdue_days
    
    total_sales = sum(inv.get("total_amount", 0) for inv in invoices)
    total_paid = sum(inv.get("total_paid", inv.get("paid_amount", 0)) for inv in invoices)
    total_pending = total_sales - total_paid
    total_interest = sum(inv.get("interest_amount", 0) for inv in invoices)
    total_outstanding = total_pending
    
    base_filter = get_company_filter(current_company)
    customers = await parties_collection.find({**base_filter, "party_type": {"$in": ["customer", "both"]}}).sort("name", 1).to_list(None) or []
    brokers = await parties_collection.find({**base_filter, "party_type": {"$in": ["broker", "both"]}}).sort("name", 1).to_list(None) or []
    qualities = await qualities_collection.find(base_filter).sort("name", 1).to_list(None) or []
    
    context.update({
        "invoices": invoices,
        "customers": customers,
        "brokers": brokers,
        "qualities": qualities,
        "customer_id": customer_id,
        "broker_id": broker_id,
        "quality": quality,
        "payment_filter": payment_filter,
        "total_sales": total_sales,
        "total_paid": total_paid,
        "total_pending": total_pending,
        "total_interest": total_interest,
        "total_outstanding": total_outstanding,
        "start_date": start_date,
        "end_date": end_date,
        "breadcrumbs": [
            {"name": "Dashboard", "url": "/dashboard"},
            {"name": "Sales Invoices", "url": "/invoices"},
            {"name": "Report", "url": "/invoices/report"}
        ]
    })
    return templates.TemplateResponse("invoices/report.html", context)

@router.get("/create")
async def create_invoice_form(
    request: Request,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company)
):
    # Get customers
    parties_collection = await get_collection("parties")
    base_filter = get_company_filter(current_company)
    customers = await parties_collection.find({
        **base_filter,
        "party_type": {"$in": ["customer", "both"]}
    }).sort("name", 1).to_list(None)
    
    # Get next invoice number
    invoices_collection = await get_collection("sales_invoices")
    last_invoice = await invoices_collection.find_one(
        base_filter,
        sort=[("invoice_no", -1)]
    )
    next_invoice_no = 1
    if last_invoice and last_invoice.get("invoice_no"):
        try:
            next_invoice_no = int(last_invoice["invoice_no"]) + 1
        except:
            next_invoice_no = 1
    
    return templates.TemplateResponse("invoices/create.html", {
        "request": request,
        "current_user": current_user,
        "current_company": current_company,
        "customers": customers,
        "next_invoice_no": next_invoice_no,
        "breadcrumbs": [
            {"name": "Dashboard", "url": "/dashboard"},
            {"name": "Sales Invoices", "url": "/invoices"},
            {"name": "Create", "url": "/invoices/create"}
        ]
    })

@router.post("/create")
async def create_invoice(
    request: Request,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company),
    customer_id: str = Form(...),
    invoice_date: str = Form(...),
    notes: str = Form(None)
):
    invoices_collection = await get_collection("sales_invoices")
    parties_collection = await get_collection("parties")
    
    # Get customer details
    customer = await parties_collection.find_one({"_id": ObjectId(customer_id)})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    # Get invoice number from form
    form_data = await request.form()
    invoice_no = form_data.get("invoice_no")
    challan_no = form_data.get("challan_no") or invoice_no
    broker_id = form_data.get("broker_id")
    broker_name = form_data.get("broker_name", "NONE")
    
    # Get items from form
    import json
    items_json = form_data.get("items", "[]")
    try:
        items = json.loads(items_json) if isinstance(items_json, str) else items_json
    except:
        raise HTTPException(status_code=400, detail="Invalid items data")
    
    if not items:
        raise HTTPException(status_code=400, detail="Items are required")
    
    subtotal = sum(item.get("taxable_amount", 0) for item in items)
    gst_total = sum(item.get("cgst", 0) + item.get("sgst", 0) + item.get("igst", 0) for item in items)
    before_round = subtotal + gst_total
    total_amount = round(before_round)
    round_off = total_amount - before_round
    
    due_days = int(form_data.get("due_days", 0))
    due_date_str = form_data.get("due_date")
    due_date = datetime.fromisoformat(due_date_str) if due_date_str else None
    
    invoice_data = {
        **get_company_filter(current_company),
        "invoice_no": invoice_no,
        "challan_no": challan_no,
        "invoice_date": datetime.fromisoformat(invoice_date),
        "customer_id": ObjectId(customer_id),
        "customer_name": customer["name"],
        "broker_id": ObjectId(broker_id) if broker_id else None,
        "broker_name": broker_name,
        "items": items,
        "freight": 0.0,
        "other_charges": 0.0,
        "round_off": round_off,
        "total_amount": total_amount,
        "due_days": due_days,
        "due_date": due_date,
        "interest_rate": customer.get("interest", 0),
        "payment_status": "unpaid",
        "paid_amount": 0.0,
        "balance_amount": total_amount,
        "terms_and_conditions": "Payment within 30 days",
        "notes": notes,
        "status": "finalized",
        "created_by": ObjectId(current_user["_id"]),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    result = await invoices_collection.insert_one(invoice_data)
    
    if result.inserted_id:
        # Log audit
        try:
            await AuditService.log_activity(
                company_id=str(current_company["_id"]),
                user_id=str(current_user["_id"]),
                username=current_user["username"],
                action="create",
                entity_type="invoice",
                entity_id=str(result.inserted_id),
                ip_address=AuditService.get_client_ip(request)
            )
        except:
            pass
        
        return RedirectResponse(url="/invoices", status_code=302)
    else:
        return templates.TemplateResponse("invoices/create.html", {
            "request": request,
            "current_user": current_user,
            "current_company": current_company,
            "error": "Failed to create invoice"
        })

@router.get("/{invoice_id}/edit")
async def edit_invoice_form(
    request: Request,
    invoice_id: str,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company)
):
    invoices_collection = await get_collection("sales_invoices")
    parties_collection = await get_collection("parties")
    
    invoice = await invoices_collection.find_one({
        "_id": ObjectId(invoice_id),
        **get_company_filter(current_company)
    })
    
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    base_filter = get_company_filter(current_company)
    customers = await parties_collection.find({
        **base_filter,
        "party_type": {"$in": ["customer", "both"]}
    }).sort("name", 1).to_list(None)
    
    return templates.TemplateResponse("invoices/edit.html", {
        "request": request,
        "current_user": current_user,
        "current_company": current_company,
        "invoice": invoice,
        "customers": customers,
        "breadcrumbs": [
            {"name": "Dashboard", "url": "/dashboard"},
            {"name": "Sales Invoices", "url": "/invoices"},
            {"name": f"Edit #{invoice.get('invoice_no', '')}", "url": f"/invoices/{invoice_id}/edit"}
        ]
    })

@router.post("/{invoice_id}/edit")
async def update_invoice(
    request: Request,
    invoice_id: str,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company),
    customer_id: str = Form(...),
    invoice_date: str = Form(...)
):
    invoices_collection = await get_collection("sales_invoices")
    parties_collection = await get_collection("parties")
    
    invoice = await invoices_collection.find_one({
        "_id": ObjectId(invoice_id),
        **get_company_filter(current_company)
    })
    
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    customer = await parties_collection.find_one({"_id": ObjectId(customer_id)})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    form_data = await request.form()
    invoice_no = form_data.get("invoice_no")
    challan_no = form_data.get("challan_no") or invoice_no
    
    import json
    items_json = form_data.get("items", "[]")
    try:
        items = json.loads(items_json) if isinstance(items_json, str) else items_json
    except:
        raise HTTPException(status_code=400, detail="Invalid items data")
    
    if not items:
        raise HTTPException(status_code=400, detail="Items are required")
    
    subtotal = sum(item.get("taxable_amount", 0) for item in items)
    gst_total = sum(item.get("cgst", 0) + item.get("sgst", 0) + item.get("igst", 0) for item in items)
    before_round = subtotal + gst_total
    total_amount = round(before_round)
    round_off = total_amount - before_round
    
    update_data = {
        "invoice_no": invoice_no,
        "challan_no": challan_no,
        "invoice_date": datetime.fromisoformat(invoice_date),
        "customer_id": ObjectId(customer_id),
        "customer_name": customer["name"],
        "items": items,
        "round_off": round_off,
        "total_amount": total_amount,
        "balance_amount": total_amount - invoice.get("paid_amount", 0),
        "updated_at": datetime.utcnow()
    }
    
    await invoices_collection.update_one(
        {"_id": ObjectId(invoice_id)},
        {"$set": update_data}
    )
    
    try:
        await AuditService.log_activity(
            company_id=str(current_company["_id"]),
            user_id=str(current_user["_id"]),
            username=current_user["username"],
            action="update",
            entity_type="invoice",
            entity_id=invoice_id,
            ip_address=AuditService.get_client_ip(request)
        )
    except:
        pass
    
    return RedirectResponse(url=f"/invoices/{invoice_id}", status_code=302)

@router.get("/{invoice_id}")
async def view_invoice(
    request: Request,
    invoice_id: str,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company)
):
    invoices_collection = await get_collection("sales_invoices")
    invoice = await invoices_collection.find_one({
        "_id": ObjectId(invoice_id),
        **get_company_filter(current_company)
    })
    
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    return templates.TemplateResponse("invoices/view.html", {
        "request": request,
        "current_user": current_user,
        "current_company": current_company,
        "invoice": invoice,
        "breadcrumbs": [
            {"name": "Dashboard", "url": "/dashboard"},
            {"name": "Sales Invoices", "url": "/invoices"},
            {"name": f"Invoice #{invoice.get('invoice_no', '')}", "url": f"/invoices/{invoice_id}"}
        ]
    })

@router.get("/{invoice_id}/print")
async def print_invoice(
    request: Request,
    invoice_id: str,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company)
):
    invoices_collection = await get_collection("sales_invoices")
    parties_collection = await get_collection("parties")
    bank_accounts_collection = await get_collection("bank_accounts")
    
    invoice = await invoices_collection.find_one({
        "_id": ObjectId(invoice_id),
        **get_company_filter(current_company)
    })
    
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    # Get customer details
    customer = await parties_collection.find_one({"_id": invoice["customer_id"]})
    if not customer:
        customer = {"name": invoice.get("customer_name", "Unknown")}
    
    # Get all bank accounts
    bank_accounts = await bank_accounts_collection.find(
        {'company_id': current_company['_id']}
    ).to_list(None)
        
    # Calculate totals
    total_taxable = sum(float(item.get("taxable_amount", 0)) for item in invoice.get("items", []))
    total_cgst = sum(float(item.get("cgst", 0)) for item in invoice.get("items", []))
    total_sgst = sum(float(item.get("sgst", 0)) for item in invoice.get("items", []))
    total_igst = sum(float(item.get("igst", 0)) for item in invoice.get("items", []))
    total_meters = sum(float(item.get("meters", 0)) for item in invoice.get("items", []))
    
    # Calculate net rate (total amount / total meters)
    net_rate = invoice.get("total_amount", 0) / total_meters if total_meters > 0 else 0
    
    # Get GST percentages (from first item)
    first_item = invoice.get("items", [{}])[0]
    gst_rate = float(first_item.get("gst_rate", 0))
    cgst_percent = gst_rate / 2 if total_cgst > 0 else 0
    sgst_percent = gst_rate / 2 if total_sgst > 0 else 0
    igst_percent = gst_rate if total_igst > 0 else 0
    
    # Convert amount to words
    amount_in_words = number_to_words(invoice.get("total_amount", 0))
    
    return templates.TemplateResponse("invoices/print.html", {
        "request": request,
        "current_user": current_user,
        "current_company": current_company,
        "invoice": invoice,
        "customer": customer,
        "bank_accounts": bank_accounts,
        "total_taxable": total_taxable,
        "total_cgst": total_cgst,
        "total_sgst": total_sgst,
        "total_igst": total_igst,
        "cgst_percent": cgst_percent,
        "sgst_percent": sgst_percent,
        "igst_percent": igst_percent,
        "net_rate": net_rate,
        "amount_in_words": amount_in_words
    })

@router.delete("/{invoice_id}")
async def delete_invoice(
    invoice_id: str,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company)
):
    from fastapi.responses import JSONResponse
    invoices_collection = await get_collection("sales_invoices")
    
    invoice = await invoices_collection.find_one({
        "_id": ObjectId(invoice_id),
        **get_company_filter(current_company)
    })
    
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    if invoice.get("payment_status") in ["paid", "partial"]:
        return JSONResponse(
            status_code=400,
            content={"error": "Cannot delete invoice with payments. Payment status: " + invoice.get("payment_status")}
        )
    
    result = await invoices_collection.delete_one({
        "_id": ObjectId(invoice_id),
        **get_company_filter(current_company)
    })
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    return JSONResponse(content={"message": "Invoice deleted successfully"})