from fastapi import APIRouter, Request, Depends, Form, HTTPException, Body
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, JSONResponse
from datetime import datetime
from bson import ObjectId
from typing import List

from app import TEMPLATES_DIR
from app.dependencies import get_current_user, get_current_company, get_company_filter, get_template_context
from app.database import get_collection
from app.services.payment_service import enrich_challans_with_payments

router = APIRouter(prefix="/purchase-invoices")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

@router.get("")
async def list_purchase_invoices(
    request: Request,
    context: dict = Depends(get_template_context),
    search: str = "",
    page: int = 1,
):
    challans_collection = await get_collection("purchase_challans")
    per_page = 25
    skip = (page - 1) * per_page

    filter_query = get_company_filter(context["current_company"])

    if search:
        from app.services.payment_service import escape_regex
        safe = escape_regex(search)
        filter_query["$or"] = [
            {"challan_no": {"$regex": safe, "$options": "i"}},
            {"supplier_name": {"$regex": safe, "$options": "i"}},
        ]

    total = await challans_collection.count_documents(filter_query)
    total_pages = max(1, -(-total // per_page))

    challans = await challans_collection.find(filter_query).sort("challan_date", -1).skip(skip).limit(per_page).to_list(per_page)

    # Bulk calculate payments — single aggregation instead of N+1 queries
    await enrich_challans_with_payments(challans)

    context.update({
        "challans": challans,
        "search": search,
        "page": page,
        "total_pages": total_pages,
        "total": total,
        "breadcrumbs": [
            {"name": "Dashboard", "url": "/dashboard"},
            {"name": "Purchase Invoices", "url": "/purchase-invoices"}
        ]
    })
    return templates.TemplateResponse("purchase_invoices/list.html", context)

@router.get("/create")
async def create_challan_form(
    request: Request,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company)
):
    parties_collection = await get_collection("parties")
    challans_collection = await get_collection("purchase_challans")
    base_filter = get_company_filter(current_company)
    
    suppliers = await parties_collection.find({
        **base_filter,
        "party_type": {"$in": ["supplier", "both"]}
    }).sort("name", 1).to_list(None)
    
    suppliers_list = []
    for s in suppliers:
        broker_info = None
        if s.get("broker_id"):
            broker = await parties_collection.find_one({"_id": s["broker_id"]})
            if broker:
                broker_info = {"id": str(broker["_id"]), "name": broker["name"]}
        
        suppliers_list.append({
            "id": str(s["_id"]),
            "name": s["name"],
            "party_code": s.get("party_code", ""),
            "broker": broker_info
        })
    
    # Get next invoice number
    last_invoice = await challans_collection.find(
        base_filter
    ).sort("invoice_no", -1).limit(1).to_list(1)
    
    next_invoice_no = "1"
    if last_invoice:
        last_no = last_invoice[0].get("invoice_no", "0")
        try:
            next_invoice_no = str(int(last_no) + 1)
        except (ValueError, TypeError):
            next_invoice_no = "1"
    
    return templates.TemplateResponse("purchase_invoices/create.html", {
        "request": request,
        "current_user": current_user,
        "current_company": current_company,
        "suppliers": suppliers_list,
        "next_invoice_no": next_invoice_no,
        "breadcrumbs": [
            {"name": "Dashboard", "url": "/dashboard"},
            {"name": "Purchase Invoices", "url": "/purchase-invoices"},
            {"name": "Create", "url": "/purchase-invoices/create"}
        ]
    })

@router.post("/create")
async def create_challan(
    request: Request,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company)
):
    form_data = await request.form()
    challans_collection = await get_collection("purchase_challans")
    parties_collection = await get_collection("parties")
    
    supplier_id = form_data.get("supplier_id")
    supplier = await parties_collection.find_one({"_id": ObjectId(supplier_id)})
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    
    # Check for duplicate invoice number
    invoice_no = form_data.get("invoice_no")
    existing_invoice = await challans_collection.find_one({
        **get_company_filter(current_company),
        "invoice_no": invoice_no
    })
    if existing_invoice:
        raise HTTPException(status_code=400, detail=f"Invoice number {invoice_no} already exists")
    
    count = await challans_collection.count_documents(get_company_filter(current_company))
    challan_no = f"{current_company.get('challan_series', 'CH')}{count + 1:04d}"
    
    items = []
    i = 0
    while f"items[{i}][quality]" in form_data:
        items.append({
            "quality": form_data.get(f"items[{i}][quality]"),
            "hsn": form_data.get(f"items[{i}][hsn]"),
            "quantity": float(form_data.get(f"items[{i}][quantity]", 0)),
            "unit": form_data.get(f"items[{i}][unit]"),
            "rate": float(form_data.get(f"items[{i}][rate]", 0)),
            "amount": float(form_data.get(f"items[{i}][amount]", 0))
        })
        i += 1
    
    subtotal = float(form_data.get("subtotal", 0))
    cgst = float(form_data.get("cgst", 0))
    sgst = float(form_data.get("sgst", 0))
    total = float(form_data.get("total", 0))
    gst_rate = (cgst + sgst) / subtotal * 100 if subtotal > 0 else 0
    
    challan_date_str = form_data.get("challan_date")
    try:
        challan_date = datetime.fromisoformat(challan_date_str)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid date format")
    
    challan_data = {
        **get_company_filter(current_company),
        "company_name": form_data.get("company_name"),
        "invoice_no": form_data.get("invoice_no"),
        "challan_no": form_data.get("challan_no", challan_no),
        "challan_date": challan_date,
        "supplier_id": ObjectId(supplier_id),
        "supplier_name": supplier["name"],
        "items": items,
        "broker_id": ObjectId(form_data.get("broker_id")) if form_data.get("broker_id") else None,
        "brokerage": float(form_data.get("brokerage") or 0),
        "freight": float(form_data.get("freight") or 0),
        "subtotal": subtotal,
        "cgst": cgst,
        "sgst": sgst,
        "gst_rate": gst_rate,
        "total_amount": total,
        "status": "finalized",
        "created_by": ObjectId(current_user["_id"]),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    result = await challans_collection.insert_one(challan_data)
    
    if result.inserted_id:
        return RedirectResponse(url="/purchase-invoices/create", status_code=302)
    else:
        raise HTTPException(status_code=500, detail="Failed to create challan")

@router.get("/qualities")
async def get_qualities(
    current_company: dict = Depends(get_current_company)
):
    qualities_collection = await get_collection("qualities")
    qualities = await qualities_collection.find(
        get_company_filter(current_company)
    ).to_list(None)
    return JSONResponse(content=[q["name"] for q in qualities] if qualities else [])

@router.post("/qualities")
async def add_quality(
    request: Request,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company)
):
    data = await request.json()
    qualities_collection = await get_collection("qualities")
    
    existing = await qualities_collection.find_one({
        **get_company_filter(current_company),
        "name": data["name"]
    })
    
    if existing:
        return JSONResponse(content={"id": str(existing["_id"]), "name": data["name"]})
    
    quality_data = {
        **get_company_filter(current_company),
        "name": data["name"],
        "created_at": datetime.utcnow()
    }
    
    result = await qualities_collection.insert_one(quality_data)
    return JSONResponse(content={"id": str(result.inserted_id), "name": data["name"]})

@router.get("/hsn-codes")
async def get_hsn_codes(
    current_company: dict = Depends(get_current_company)
):
    hsn_collection = await get_collection("hsn_codes")
    hsn_codes = await hsn_collection.find(
        get_company_filter(current_company)
    ).to_list(None)
    return JSONResponse(content=[h["code"] for h in hsn_codes] if hsn_codes else [])

@router.post("/hsn-codes")
async def add_hsn_code(
    request: Request,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company)
):
    data = await request.json()
    hsn_collection = await get_collection("hsn_codes")
    
    existing = await hsn_collection.find_one({
        **get_company_filter(current_company),
        "code": data["code"]
    })
    
    if existing:
        return JSONResponse(content={"id": str(existing["_id"]), "code": data["code"]})
    
    hsn_data = {
        **get_company_filter(current_company),
        "code": data["code"],
        "description": data.get("description", ""),
        "created_at": datetime.utcnow()
    }
    
    result = await hsn_collection.insert_one(hsn_data)
    return JSONResponse(content={"id": str(result.inserted_id), "code": data["code"]})

@router.get("/{challan_id}")
async def view_challan(
    request: Request,
    challan_id: str,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company)
):
    challans_collection = await get_collection("purchase_challans")
    parties_collection = await get_collection("parties")
    
    challan = await challans_collection.find_one({
        "_id": ObjectId(challan_id),
        **get_company_filter(current_company)
    })
    
    if not challan:
        raise HTTPException(status_code=404, detail="Challan not found")
    
    # Get broker name if broker_id exists
    if challan.get("broker_id"):
        broker = await parties_collection.find_one({"_id": challan["broker_id"]})
        if broker:
            challan["broker_name"] = broker["name"]
    
    return templates.TemplateResponse("purchase_invoices/view.html", {
        "request": request,
        "current_user": current_user,
        "current_company": current_company,
        "challan": challan,
        "breadcrumbs": [
            {"name": "Dashboard", "url": "/dashboard"},
            {"name": "Purchase Invoices", "url": "/purchase-invoices"},
            {"name": challan.get("challan_no", "View"), "url": f"/purchase-invoices/{challan_id}"}
        ]
    })

@router.post("/{challan_id}/delete")
async def delete_challan(
    challan_id: str,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company)
):
    challans_collection = await get_collection("purchase_challans")
    
    result = await challans_collection.delete_one({
        "_id": ObjectId(challan_id),
        **get_company_filter(current_company)
    })
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Challan not found")
    
    return RedirectResponse(url="/purchase-invoices", status_code=302)