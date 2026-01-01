from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from bson import ObjectId
from datetime import datetime
from app.dependencies import get_current_user, get_current_company, get_company_filter
from app.database import get_collection

templates = Jinja2Templates(directory="app/templates")

router = APIRouter(prefix="/reports", tags=["reports"])

@router.get("/generator", response_class=HTMLResponse)
async def report_generator(request: Request, current_user: dict = Depends(get_current_user), current_company: dict = Depends(get_current_company)):
    companies_collection = await get_collection("companies")
    parties_collection = await get_collection("parties")
    qualities_collection = await get_collection("qualities")
    
    user_companies = await companies_collection.find(
        {"_id": {"$in": [ObjectId(cid) for cid in current_user.get("companies", [])]}}
    ).to_list(None)
    
    suppliers_raw = await parties_collection.find({
        **get_company_filter(current_company),
        "party_type": {"$in": ["supplier", "both"]}
    }).sort("name", 1).to_list(None)
    
    suppliers = []
    for s in suppliers_raw:
        supplier_dict = {"_id": str(s["_id"]), "name": s["name"]}
        if s.get("broker_id"):
            supplier_dict["broker_id"] = str(s["broker_id"])
        suppliers.append(supplier_dict)
    
    qualities = await qualities_collection.find(get_company_filter(current_company)).to_list(None)
    
    return templates.TemplateResponse("reports/generator.html", {
        "request": request,
        "current_user": current_user,
        "current_company": current_company,
        "user_companies": user_companies,
        "suppliers": suppliers,
        "qualities": qualities,
        "breadcrumbs": [
            {"name": "Dashboard", "url": "/dashboard"},
            {"name": "Report Generator", "url": "/reports/generator"}
        ]
    })

@router.get("/preview", response_class=HTMLResponse)
async def preview_report(
    request: Request,
    company: str = Query(None),
    supplier: str = Query(None),
    quality: str = Query(None),
    fromDate: str = Query(None),
    toDate: str = Query(None),
    filter: str = Query("all"),
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company)
):
    challans_collection = await get_collection("purchase_challans")
    parties_collection = await get_collection("parties")
    
    query = get_company_filter(current_company)
    
    if supplier:
        query["supplier_id"] = ObjectId(supplier)
    
    if quality:
        query["items.quality"] = quality
    
    if fromDate:
        query["challan_date"] = {"$gte": datetime.fromisoformat(fromDate)}
    if toDate:
        if "challan_date" in query:
            query["challan_date"]["$lte"] = datetime.fromisoformat(toDate)
        else:
            query["challan_date"] = {"$lte": datetime.fromisoformat(toDate)}
    
    challans = await challans_collection.find(query).sort("challan_date", -1).to_list(None)
    payments_collection = await get_collection("payments")
    
    for challan in challans:
        if challan.get("broker_id"):
            broker = await parties_collection.find_one({"_id": challan["broker_id"]})
            if broker:
                challan["broker_name"] = broker["name"]
        
        existing_payments = await payments_collection.find({"invoices.challan_id": challan["_id"]}).to_list(None)
        total_paid = sum(
            inv["amount"] for p in existing_payments 
            for inv in p.get("invoices", []) 
            if inv["challan_id"] == challan["_id"]
        )
        challan["total_paid"] = total_paid
        challan["outstanding"] = challan.get("total_amount", 0) - total_paid
        
        payment_details = []
        for p in existing_payments:
            for inv in p.get("invoices", []):
                if inv["challan_id"] == challan["_id"]:
                    mode = p.get("payment_type", "")
                    cheque = p.get("cheque_no", "") if mode == "cheque" else ""
                    payment_details.append(f"{mode.title()}{' - ' + cheque if cheque else ''}")
        challan["payment_mode"] = ", ".join(payment_details) if payment_details else "-"
    
    supplier_name = "All Suppliers"
    if supplier:
        supplier_doc = await parties_collection.find_one({"_id": ObjectId(supplier)})
        if supplier_doc:
            supplier_name = supplier_doc["name"]
    
    return templates.TemplateResponse("reports/preview.html", {
        "request": request,
        "current_user": current_user,
        "current_company": current_company,
        "challans": challans,
        "supplier_name": supplier_name,
        "quality": quality or "All",
        "fromDate": fromDate,
        "toDate": toDate,
        "filter": filter
    })

@router.get("/preview-inline", response_class=HTMLResponse)
async def preview_inline(
    request: Request,
    supplier: str = Query(None),
    quality: str = Query(None),
    fromDate: str = Query(None),
    toDate: str = Query(None),
    filter: str = Query("all"),
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company)
):
    challans_collection = await get_collection("purchase_challans")
    parties_collection = await get_collection("parties")
    payments_collection = await get_collection("payments")
    
    query = get_company_filter(current_company)
    
    if supplier:
        query["supplier_id"] = ObjectId(supplier)
    
    if quality:
        query["items.quality"] = quality
    
    if fromDate:
        query["challan_date"] = {"$gte": datetime.fromisoformat(fromDate)}
    if toDate:
        if "challan_date" in query:
            query["challan_date"]["$lte"] = datetime.fromisoformat(toDate)
        else:
            query["challan_date"] = {"$lte": datetime.fromisoformat(toDate)}
    
    challans = await challans_collection.find(query).sort("challan_date", -1).to_list(None)
    
    for challan in challans:
        if challan.get("broker_id"):
            broker = await parties_collection.find_one({"_id": challan["broker_id"]})
            if broker:
                challan["broker_name"] = broker["name"]
        
        existing_payments = await payments_collection.find({"invoices.challan_id": challan["_id"]}).to_list(None)
        total_paid = sum(
            inv["amount"] for p in existing_payments 
            for inv in p.get("invoices", []) 
            if inv["challan_id"] == challan["_id"]
        )
        challan["total_paid"] = total_paid
        challan["outstanding"] = challan.get("total_amount", 0) - total_paid
        
        payment_details = []
        for p in existing_payments:
            for inv in p.get("invoices", []):
                if inv["challan_id"] == challan["_id"]:
                    mode = p.get("payment_type", "")
                    cheque = p.get("cheque_no", "") if mode == "cheque" else ""
                    payment_details.append(f"{mode.title()}{' - ' + cheque if cheque else ''}")
        challan["payment_mode"] = ", ".join(payment_details) if payment_details else "-"
    
    supplier_name = "All Suppliers"
    if supplier:
        supplier_doc = await parties_collection.find_one({"_id": ObjectId(supplier)})
        if supplier_doc:
            supplier_name = supplier_doc["name"]
    
    return templates.TemplateResponse("reports/preview_inline.html", {
        "request": request,
        "current_company": current_company,
        "challans": challans,
        "supplier_name": supplier_name,
        "quality": quality or "All",
        "fromDate": fromDate,
        "toDate": toDate,
        "filter": filter
    })

@router.get("/export-pdf")
async def export_pdf(
    company: str = Query(None),
    supplier: str = Query(None),
    quality: str = Query(None),
    fromDate: str = Query(None),
    toDate: str = Query(None),
    filter: str = Query("all"),
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company)
):
    challans_collection = await get_collection("purchase_challans")
    parties_collection = await get_collection("parties")
    
    query = get_company_filter(current_company)
    
    if supplier:
        query["supplier_id"] = ObjectId(supplier)
    
    if quality:
        query["items.quality"] = quality
    
    if fromDate:
        query["challan_date"] = {"$gte": datetime.fromisoformat(fromDate)}
    if toDate:
        if "challan_date" in query:
            query["challan_date"]["$lte"] = datetime.fromisoformat(toDate)
        else:
            query["challan_date"] = {"$lte": datetime.fromisoformat(toDate)}
    
    challans = await challans_collection.find(query).sort("challan_date", -1).to_list(None)
    
    csv_content = "Challan No,Date,Supplier,Quality,Quantity,Amount\n"
    for challan in challans:
        for item in challan.get("items", []):
            csv_content += f"{challan.get('challan_no','')},{challan.get('challan_date','').strftime('%Y-%m-%d') if challan.get('challan_date') else ''},{challan.get('supplier_name','')},{item.get('quality','')},{item.get('quantity','')},{item.get('amount','')}\n"
    
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"}
    )
