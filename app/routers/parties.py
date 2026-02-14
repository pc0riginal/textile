from fastapi import APIRouter, Request, Depends, Form, Query, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, JSONResponse
from datetime import datetime
from bson import ObjectId
from typing import Optional

from app import TEMPLATES_DIR
from app.dependencies import get_current_user, get_current_company, get_template_context
from app.database import get_collection
from app.services.payment_service import escape_regex
import re

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)

@router.get("")
async def list_parties(
    request: Request,
    context: dict = Depends(get_template_context),
    party_type: Optional[str] = Query(None),
    search: str = "",
    page: int = 1,
):
    parties_collection = await get_collection("parties")
    per_page = 25
    skip = (page - 1) * per_page

    filter_query = {}
    if party_type:
        filter_query["party_type"] = party_type

    if search:
        safe = escape_regex(search)
        filter_query["$or"] = [
            {"name": {"$regex": safe, "$options": "i"}},
            {"party_code": {"$regex": safe, "$options": "i"}},
            {"contact.phone": {"$regex": safe, "$options": "i"}},
            {"gstin": {"$regex": safe, "$options": "i"}},
        ]

    total = await parties_collection.count_documents(filter_query)
    total_pages = max(1, -(-total // per_page))

    parties = await parties_collection.find(filter_query).sort("name", 1).skip(skip).limit(per_page).to_list(per_page)

    context.update({
        "parties": parties,
        "selected_type": party_type,
        "search": search,
        "page": page,
        "total_pages": total_pages,
        "total": total,
        "breadcrumbs": [
            {"name": "Dashboard", "url": "/dashboard"},
            {"name": "Parties", "url": "/parties"}
        ]
    })
    return templates.TemplateResponse("parties/list.html", context)

@router.get("/create")
async def create_party_form(
    request: Request,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company),
    type: Optional[str] = Query(None),
    redirect: Optional[str] = Query(None)
):
    parties_collection = await get_collection("parties")
    
    brokers = await parties_collection.find({
        "party_type": "broker"
    }).sort("name", 1).to_list(None)
    
    indian_states = [
        "ANDHRA PRADESH", "ARUNACHAL PRADESH", "ASSAM", "BIHAR", "CHHATTISGARH",
        "GOA", "GUJARAT", "HARYANA", "HIMACHAL PRADESH", "JHARKHAND", "KARNATAKA",
        "KERALA", "MADHYA PRADESH", "MAHARASHTRA", "MANIPUR", "MEGHALAYA", "MIZORAM",
        "NAGALAND", "ODISHA", "PUNJAB", "RAJASTHAN", "SIKKIM", "TAMIL NADU",
        "TELANGANA", "TRIPURA", "UTTAR PRADESH", "UTTARAKHAND", "WEST BENGAL"
    ]
    
    return templates.TemplateResponse("parties/create.html", {
        "request": request,
        "current_user": current_user,
        "current_company": current_company,
        "brokers": brokers,
        "indian_states": indian_states,
        "default_type": type,
        "redirect_url": redirect,
        "breadcrumbs": [
            {"name": "Dashboard", "url": "/dashboard"},
            {"name": "Parties", "url": "/parties"},
            {"name": "Create", "url": "/parties/create"}
        ]
    })

@router.post("/create")
async def create_party(
    request: Request,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company),
    name: str = Form(...),
    party_type: str = Form(...),
    party_code: str = Form(None),
    gstin: str = Form(None),
    pan: str = Form(None),
    delivery_address: str = Form(None),
    delivery_city: str = Form(None),
    delivery_pincode: str = Form(None),
    delivery_state: str = Form("GUJARAT"),
    office_address: str = Form(None),
    office_city: str = Form(None),
    office_pincode: str = Form(None),
    office_state: str = Form("GUJARAT"),
    phone: str = Form(...),
    email: str = Form(None),
    contact_person: str = Form(None),
    broker_id: str = Form(None),
    brokerage: float = Form(0.0),
    dhara_day: int = Form(0),
    interest: float = Form(0.0),
    redirect_url: str = Form(None)
):
    parties_collection = await get_collection("parties")
    
    if not party_code:
        count = await parties_collection.count_documents({})
        party_code = f"P{count + 1:04d}"
    
    party_data = {
        "name": name,
        "party_type": party_type,
        "party_code": party_code,
        "gstin": gstin,
        "pan": pan,
        "delivery_address": delivery_address,
        "delivery_city": delivery_city,
        "delivery_pincode": delivery_pincode,
        "delivery_state": delivery_state,
        "office_address": office_address,
        "office_city": office_city,
        "office_pincode": office_pincode,
        "office_state": office_state,
        "contact": {
            "phone": phone,
            "email": email,
            "contact_person": contact_person
        },
        "broker_id": ObjectId(broker_id) if broker_id else None,
        "brokerage": brokerage,
        "dhara_day": dhara_day,
        "interest": interest,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    result = await parties_collection.insert_one(party_data)
    
    if result.inserted_id:
        redirect_to = redirect_url if redirect_url else "/parties"
        return RedirectResponse(url=redirect_to, status_code=302)
    else:
        return templates.TemplateResponse("parties/create.html", {
            "request": request,
            "current_user": current_user,
            "current_company": current_company,
            "error": "Failed to create party"
        })

@router.post("/api/quick-add")
async def quick_add_party(
    request: Request,
    current_company: dict = Depends(get_current_company)
):
    data = await request.json()
    
    # Backend validation
    errors = []
    name = (data.get("name") or "").strip()
    if not name:
        errors.append("Party name is required")
    
    phone = (data.get("phone") or "").strip()
    if phone and not re.match(r'^\d{10}$', phone):
        errors.append("Mobile must be 10 digits")
    
    gstin = (data.get("gstin") or "").strip()
    if gstin and not re.match(r'^\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d]$', gstin, re.IGNORECASE):
        errors.append("GSTIN format invalid")
    
    delivery_pincode = (data.get("delivery_pincode") or "").strip()
    if delivery_pincode and not re.match(r'^\d{6}$', delivery_pincode):
        errors.append("Delivery pincode must be 6 digits")
    
    office_pincode = (data.get("office_pincode") or "").strip()
    if office_pincode and not re.match(r'^\d{6}$', office_pincode):
        errors.append("Office pincode must be 6 digits")
    
    email = (data.get("email") or "").strip()
    if email and not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', email):
        errors.append("Email format invalid")
    
    if errors:
        return JSONResponse(status_code=422, content={"detail": "; ".join(errors)})
    
    parties_collection = await get_collection("parties")
    
    existing = await parties_collection.find_one({
        "name": data["name"],
        "party_type": data.get("party_type", "customer")
    })
    
    if existing:
        return JSONResponse(content={"id": str(existing["_id"]), "name": existing["name"]})
    
    count = await parties_collection.count_documents({})
    party_code = f"P{count + 1:04d}"
    
    party_data = {
        "name": data["name"],
        "party_type": data.get("party_type", "customer"),
        "party_code": data.get("party_code") or party_code,
        "gstin": data.get("gstin", ""),
        "delivery_address": data.get("delivery_address", ""),
        "delivery_city": data.get("delivery_city", ""),
        "delivery_pincode": data.get("delivery_pincode", ""),
        "delivery_state": data.get("delivery_state", "GUJARAT"),
        "office_address": data.get("office_address", ""),
        "office_city": data.get("office_city", ""),
        "office_pincode": data.get("office_pincode", ""),
        "office_state": data.get("office_state", "GUJARAT"),
        "contact": {
            "phone": data.get("phone", ""),
            "email": data.get("email", "")
        },
        "broker_id": ObjectId(data["broker_id"]) if data.get("broker_id") else None,
        "brokerage": float(data.get("brokerage", 0)),
        "dhara_day": int(data.get("dhara_day", 0)),
        "interest": float(data.get("interest", 0)),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    result = await parties_collection.insert_one(party_data)
    return JSONResponse(content={"id": str(result.inserted_id), "name": data["name"]})

@router.post("/quick-add-full")
async def quick_add_full_party(
    request: Request,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company)
):
    data = await request.json()
    
    # Backend validation
    errors = []
    name = (data.get("name") or "").strip()
    if not name:
        errors.append("Name is required")
    
    phone = (data.get("phone") or "").strip()
    if phone and not re.match(r'^\d{10}$', phone):
        errors.append("Phone must be 10 digits")
    
    gstin = (data.get("gstin") or "").strip()
    if gstin and not re.match(r'^\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d]$', gstin, re.IGNORECASE):
        errors.append("GSTIN format invalid")
    
    pan = (data.get("pan") or "").strip()
    if pan and not re.match(r'^[A-Z]{5}\d{4}[A-Z]$', pan, re.IGNORECASE):
        errors.append("PAN format invalid")
    
    pincode = (data.get("pincode") or "").strip()
    if pincode and not re.match(r'^\d{6}$', pincode):
        errors.append("Pincode must be 6 digits")
    
    if errors:
        return JSONResponse(status_code=422, content={"detail": "; ".join(errors)})
    
    parties_collection = await get_collection("parties")
    
    count = await parties_collection.count_documents({})
    party_code = f"P{count + 1:04d}"
    
    party_data = {
        "name": data["name"],
        "party_type": data["party_type"],
        "party_code": party_code,
        "gstin": data.get("gstin", ""),
        "pan": data.get("pan", ""),
        "address": {
            "line1": data.get("address_line1", ""),
            "line2": "",
            "city": data.get("city", ""),
            "state": data.get("state", ""),
            "pincode": data.get("pincode", "")
        },
        "contact": {"phone": data.get("phone", ""), "email": ""},
        "credit_limit": 0.0,
        "opening_balance": 0.0,
        "current_balance": 0.0,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    result = await parties_collection.insert_one(party_data)
    
    response_data = {
        "supplier": {
            "id": str(result.inserted_id),
            "name": data["name"],
            "party_code": party_code
        }
    }
    
    if data.get("broker_name"):
        existing_broker = await parties_collection.find_one({
            "party_type": "broker",
            "name": data["broker_name"]
        })
        
        if existing_broker:
            broker_id = existing_broker["_id"]
            response_data["broker"] = {
                "id": str(broker_id),
                "name": data["broker_name"]
            }
        else:
            broker_count = await parties_collection.count_documents({})
            broker_code = f"P{broker_count + 1:04d}"
            
            broker_data = {
                "name": data["broker_name"],
                "party_type": "broker",
                "party_code": broker_code,
                "address": {"line1": "-", "city": "-", "state": "-", "pincode": "-"},
                "contact": {"phone": "-"},
                "credit_limit": 0.0,
                "opening_balance": 0.0,
                "current_balance": 0.0,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            broker_result = await parties_collection.insert_one(broker_data)
            broker_id = broker_result.inserted_id
            response_data["broker"] = {
                "id": str(broker_id),
                "name": data["broker_name"]
            }
        
        await parties_collection.update_one(
            {"_id": result.inserted_id},
            {"$set": {"broker_id": broker_id}}
        )
    
    return JSONResponse(content=response_data)

@router.get("/api/list")
async def get_parties_api(
    current_company: dict = Depends(get_current_company),
    party_type: Optional[str] = Query(None)
):
    parties_collection = await get_collection("parties")
    filter_query = {}
    if party_type:
        filter_query["party_type"] = party_type
    
    parties = await parties_collection.find(filter_query).sort("name", 1).to_list(None)
    
    for p in parties:
        p["_id"] = str(p["_id"])
        if "company_id" in p:
            p["company_id"] = str(p["company_id"])
        if "broker_id" in p and p["broker_id"]:
            p["broker_id"] = str(p["broker_id"])
        if "created_at" in p:
            del p["created_at"]
        if "updated_at" in p:
            del p["updated_at"]
    
    return JSONResponse(content=parties)

@router.get("/api/brokers")
async def get_brokers(
    current_company: dict = Depends(get_current_company)
):
    parties_collection = await get_collection("parties")
    brokers = await parties_collection.find({
        "party_type": "broker"
    }).sort("name", 1).to_list(None)
    
    for broker in brokers:
        broker["id"] = str(broker["_id"])
        del broker["_id"]
        if "company_id" in broker:
            broker["company_id"] = str(broker["company_id"])
        if "broker_id" in broker and broker["broker_id"]:
            broker["broker_id"] = str(broker["broker_id"])
        if "created_at" in broker:
            del broker["created_at"]
        if "updated_at" in broker:
            del broker["updated_at"]
    
    return JSONResponse(content=brokers)

@router.get("/search")
async def search_parties(
    q: str = Query(...),
    current_company: dict = Depends(get_current_company)
):
    safe_q = escape_regex(q)
    parties_collection = await get_collection("parties")
    
    parties = await parties_collection.find({
        "$or": [
            {"name": {"$regex": safe_q, "$options": "i"}},
            {"party_code": {"$regex": safe_q, "$options": "i"}},
            {"contact.phone": {"$regex": safe_q, "$options": "i"}}
        ]
    }).limit(10).to_list(10)
    
    for party in parties:
        party["id"] = str(party["_id"])
        del party["_id"]
        if "company_id" in party:
            party["company_id"] = str(party["company_id"])
    
    return JSONResponse(content=parties)

@router.get("/{party_id}/edit")
async def edit_party_form(
    request: Request,
    party_id: str,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company)
):
    parties_collection = await get_collection("parties")
    party = await parties_collection.find_one({"_id": ObjectId(party_id)})
    
    if not party:
        raise HTTPException(status_code=404, detail="Party not found")
    
    brokers = await parties_collection.find({
        "party_type": "broker"
    }).sort("name", 1).to_list(None)
    
    indian_states = [
        "ANDHRA PRADESH", "ARUNACHAL PRADESH", "ASSAM", "BIHAR", "CHHATTISGARH",
        "GOA", "GUJARAT", "HARYANA", "HIMACHAL PRADESH", "JHARKHAND", "KARNATAKA",
        "KERALA", "MADHYA PRADESH", "MAHARASHTRA", "MANIPUR", "MEGHALAYA", "MIZORAM",
        "NAGALAND", "ODISHA", "PUNJAB", "RAJASTHAN", "SIKKIM", "TAMIL NADU",
        "TELANGANA", "TRIPURA", "UTTAR PRADESH", "UTTARAKHAND", "WEST BENGAL"
    ]
    
    return templates.TemplateResponse("parties/edit.html", {
        "request": request,
        "current_user": current_user,
        "current_company": current_company,
        "party": party,
        "brokers": brokers,
        "indian_states": indian_states,
        "breadcrumbs": [
            {"name": "Dashboard", "url": "/dashboard"},
            {"name": "Parties", "url": "/parties"},
            {"name": "Edit", "url": f"/parties/{party_id}/edit"}
        ]
    })

@router.post("/{party_id}/edit")
async def update_party(
    party_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company),
    name: str = Form(...),
    party_type: str = Form(...),
    party_code: str = Form(None),
    gstin: str = Form(None),
    delivery_address: str = Form(None),
    delivery_city: str = Form(None),
    delivery_pincode: str = Form(None),
    delivery_state: str = Form("GUJARAT"),
    office_address: str = Form(None),
    office_city: str = Form(None),
    phone: str = Form(...),
    email: str = Form(None),
    broker_id: str = Form(None),
    brokerage: float = Form(0.0),
    dhara_day: int = Form(0),
    interest: float = Form(0.0)
):
    parties_collection = await get_collection("parties")
    
    update_data = {
        "name": name,
        "party_type": party_type,
        "party_code": party_code,
        "gstin": gstin,
        "delivery_address": delivery_address,
        "delivery_city": delivery_city,
        "delivery_pincode": delivery_pincode,
        "delivery_state": delivery_state,
        "office_address": office_address,
        "office_city": office_city,
        "contact": {"phone": phone, "email": email},
        "broker_id": ObjectId(broker_id) if broker_id else None,
        "brokerage": brokerage,
        "dhara_day": dhara_day,
        "interest": interest,
        "updated_at": datetime.utcnow()
    }
    
    result = await parties_collection.update_one(
        {"_id": ObjectId(party_id)},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Party not found")
    
    return RedirectResponse(url="/parties", status_code=302)

@router.get("/{party_id}")
async def view_party(
    request: Request,
    party_id: str,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company)
):
    parties_collection = await get_collection("parties")
    party = await parties_collection.find_one({"_id": ObjectId(party_id)})
    
    if not party:
        raise HTTPException(status_code=404, detail="Party not found")
    
    broker = None
    if party.get("broker_id"):
        broker = await parties_collection.find_one({"_id": party["broker_id"]})
    
    return templates.TemplateResponse("parties/view.html", {
        "request": request,
        "current_user": current_user,
        "current_company": current_company,
        "party": party,
        "broker": broker,
        "breadcrumbs": [
            {"name": "Dashboard", "url": "/dashboard"},
            {"name": "Parties", "url": "/parties"},
            {"name": party["name"], "url": f"/parties/{party_id}"}
        ]
    })

@router.get("/api/party-banks")
async def get_party_banks(
    current_company: dict = Depends(get_current_company)
):
    party_banks_collection = await get_collection("party_banks")
    banks = await party_banks_collection.find({}).sort("bank_name", 1).to_list(None)
    return JSONResponse(content=[b["bank_name"] for b in banks])

@router.post("/api/add-party-bank")
async def add_party_bank(
    request: Request,
    current_company: dict = Depends(get_current_company)
):
    data = await request.json()
    party_banks_collection = await get_collection("party_banks")
    
    existing = await party_banks_collection.find_one({
        "bank_name": data["bank_name"]
    })
    
    if not existing:
        await party_banks_collection.insert_one({
            "bank_name": data["bank_name"],
            "created_at": datetime.utcnow()
        })
    
    return JSONResponse(content={"success": True})

@router.get("/api/{party_id}")
async def get_party_api(
    party_id: str,
    current_company: dict = Depends(get_current_company)
):
    parties_collection = await get_collection("parties")
    party = await parties_collection.find_one({"_id": ObjectId(party_id)})
    
    if not party:
        raise HTTPException(status_code=404, detail="Party not found")
    
    party["id"] = str(party["_id"])
    del party["_id"]
    if "company_id" in party:
        party["company_id"] = str(party["company_id"])
    if "broker_id" in party and party["broker_id"]:
        party["broker_id"] = str(party["broker_id"])
    if "created_at" in party:
        del party["created_at"]
    if "updated_at" in party:
        del party["updated_at"]
    
    return JSONResponse(content=party)

@router.delete("/{party_id}")
async def delete_party(
    party_id: str,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company)
):
    parties_collection = await get_collection("parties")
    result = await parties_collection.delete_one({"_id": ObjectId(party_id)})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Party not found")
    
    return JSONResponse(content={"message": "Party deleted successfully"})
