from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from datetime import datetime
from bson import ObjectId

from app.dependencies import get_current_user, get_current_company_optional, get_template_context
from app.database import get_collection
from app.models.company import CompanyCreate, Address, Contact

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("")
async def list_companies(
    context: dict = Depends(get_template_context)
):
    context.update({
        "companies": context["user_companies"],
        "breadcrumbs": [
            {"name": "Dashboard", "url": "/dashboard"},
            {"name": "Companies", "url": "/companies"}
        ]
    })
    return templates.TemplateResponse("companies/list.html", context)

@router.get("/new")
@router.get("/create")
async def create_company_form(
    request: Request,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company_optional)
):
    companies_collection = await get_collection("companies")
    user_companies = await companies_collection.find({"_id": {"$in": [ObjectId(cid) for cid in current_user.get("companies", [])]}}).to_list(None)
    
    return templates.TemplateResponse("companies/create.html", {
        "request": request,
        "current_user": current_user,
        "current_company": current_company,
        "user_companies": user_companies,
        "financial_years": [],
        "breadcrumbs": [
            {"name": "Dashboard", "url": "/dashboard"},
            {"name": "Companies", "url": "/companies"},
            {"name": "Create", "url": "/companies/create"}
        ]
    })

@router.post("/create")
async def create_company(
    request: Request,
    current_user: dict = Depends(get_current_user),
    name: str = Form(...),
    gstin: str = Form(...),
    pan: str = Form(None),
    address_line1: str = Form(...),
    address_line2: str = Form(None),
    city: str = Form(None),
    state: str = Form(None),
    pincode: str = Form(None),
    phone: str = Form(...),
    email: str = Form(None),
    website: str = Form(None),
    financial_year: str = Form(...),
    invoice_series: str = Form("INV"),
    challan_series: str = Form("CH")
):
    import re
    errors = []
    
    # Validate mandatory fields
    if not name or not name.strip():
        errors.append("Company name is required")
    if not gstin or not gstin.strip():
        errors.append("GSTIN is required")
    elif len(gstin.strip()) != 15:
        errors.append("GSTIN must be 15 characters")
    if not address_line1 or not address_line1.strip():
        errors.append("Address line 1 is required")
    if not phone or not phone.strip():
        errors.append("Phone is required")
    
    # Validate financial year
    if not financial_year or not financial_year.strip():
        errors.append("Financial year is required")
    elif not re.match(r'^\d{4}-\d{4}$', financial_year):
        errors.append("Financial year must be in format YYYY-YYYY")
    else:
        try:
            start_year, end_year = map(int, financial_year.split('-'))
            if end_year != start_year + 1:
                errors.append("End year must be start year + 1")
        except ValueError:
            errors.append("Invalid financial year format")
    
    # Validate optional fields if provided
    if pan and len(pan.strip()) != 10:
        errors.append("PAN must be 10 characters")
    if email and not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email):
        errors.append("Invalid email format")
    if phone and not re.match(r'^[0-9]{10}$', phone):
        errors.append("Phone must be exactly 10 digits")
    if pincode and not re.match(r'^[0-9]{6}$', pincode):
        errors.append("Pincode must be 6 digits")
    
    if errors:
        return templates.TemplateResponse("companies/create.html", {
            "request": request,
            "current_user": current_user,
            "error": ", ".join(errors)
        })
    
    companies_collection = await get_collection("companies")
    users_collection = await get_collection("users")
    
    # Create company document
    company_data = {
        "name": name,
        "gstin": gstin,
        "pan": pan,
        "address": {
            "line1": address_line1,
            "line2": address_line2,
            "city": city,
            "state": state,
            "pincode": pincode
        },
        "contact": {
            "phone": phone,
            "email": email,
            "website": website
        },
        "bank_details": [],
        "logo_url": None,
        "financial_year": financial_year,
        "financial_years": [financial_year],
        "invoice_series": invoice_series,
        "challan_series": challan_series,
        "created_by": ObjectId(current_user["_id"]),
        "created_at": datetime.utcnow()
    }
    
    result = await companies_collection.insert_one(company_data)
    
    if result.inserted_id:
        # Add company to user's companies list
        await users_collection.update_one(
            {"_id": ObjectId(current_user["_id"])},
            {"$push": {"companies": result.inserted_id}}
        )
        
        return RedirectResponse(url="/companies", status_code=302)
    else:
        return templates.TemplateResponse("companies/create.html", {
            "request": request,
            "current_user": current_user,
            "error": "Failed to create company"
        })

@router.get("/{company_id}/edit")
async def edit_company_form(
    company_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    companies_collection = await get_collection("companies")
    company = await companies_collection.find_one({"_id": ObjectId(company_id)})
    
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    return templates.TemplateResponse("companies/edit.html", {
        "request": request,
        "current_user": current_user,
        "company": company
    })

@router.post("/{company_id}/edit")
async def edit_company(
    company_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
    name: str = Form(...),
    gstin: str = Form(...),
    pan: str = Form(None),
    address_line1: str = Form(...),
    address_line2: str = Form(None),
    city: str = Form(None),
    state: str = Form(None),
    pincode: str = Form(None),
    phone: str = Form(...),
    email: str = Form(None)
):
    import re
    errors = []
    
    # Validate mandatory fields
    if not name or not name.strip():
        errors.append("Company name is required")
    if not gstin or not gstin.strip():
        errors.append("GSTIN is required")
    elif len(gstin.strip()) != 15:
        errors.append("GSTIN must be 15 characters")
    if not address_line1 or not address_line1.strip():
        errors.append("Address line 1 is required")
    if not phone or not phone.strip():
        errors.append("Phone is required")
    
    # Validate optional fields if provided
    if pan and len(pan.strip()) != 10:
        errors.append("PAN must be 10 characters")
    if email and not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email):
        errors.append("Invalid email format")
    if phone and not re.match(r'^[0-9]{10}$', phone):
        errors.append("Phone must be exactly 10 digits")
    if pincode and not re.match(r'^[0-9]{6}$', pincode):
        errors.append("Pincode must be 6 digits")
    
    if errors:
        companies_collection = await get_collection("companies")
        company = await companies_collection.find_one({"_id": ObjectId(company_id)})
        return templates.TemplateResponse("companies/edit.html", {
            "request": request,
            "current_user": current_user,
            "company": company,
            "error": ", ".join(errors)
        })
    
    companies_collection = await get_collection("companies")
    
    await companies_collection.update_one(
        {"_id": ObjectId(company_id)},
        {"$set": {
            "name": name,
            "gstin": gstin,
            "pan": pan,
            "address.line1": address_line1,
            "address.line2": address_line2,
            "address.city": city,
            "address.state": state,
            "address.pincode": pincode,
            "contact.phone": phone,
            "contact.email": email,
            "updated_at": datetime.utcnow()
        }}
    )
    
    return RedirectResponse(url="/companies", status_code=302)

@router.post("/add-financial-year")
async def add_financial_year(
    request: Request,
    current_user: dict = Depends(get_current_user),
    company_id: str = Form(...),
    financial_year: str = Form(...)
):
    import re
    from fastapi.responses import HTMLResponse
    
    # Validate financial year
    if not financial_year or not financial_year.strip():
        return HTMLResponse(content=f'<script>alert("Financial year is required"); window.location.href="/dashboard";</script>')
    if not re.match(r'^\d{4}-\d{4}$', financial_year):
        return HTMLResponse(content=f'<script>alert("Financial year must be in format YYYY-YYYY (e.g., 2025-2026)"); window.location.href="/dashboard";</script>')
    
    try:
        start_year, end_year = map(int, financial_year.split('-'))
        if end_year != start_year + 1:
            return HTMLResponse(content=f'<script>alert("End year must be start year + 1"); window.location.href="/dashboard";</script>')
    except ValueError:
        return HTMLResponse(content=f'<script>alert("Invalid financial year format"); window.location.href="/dashboard";</script>')
    
    companies_collection = await get_collection("companies")
    
    # Check if financial year already exists
    company = await companies_collection.find_one({"_id": ObjectId(company_id)})
    if not company:
        return HTMLResponse(content=f'<script>alert("Company not found"); window.location.href="/dashboard";</script>')
    
    if financial_year in company.get("financial_years", []):
        return HTMLResponse(content=f'<script>alert("Financial year {financial_year} already exists"); window.location.href="/dashboard";</script>')
    
    # Add financial year and set as current
    await companies_collection.update_one(
        {"_id": ObjectId(company_id)},
        {
            "$set": {"financial_year": financial_year},
            "$addToSet": {"financial_years": financial_year}
        }
    )
    
    return HTMLResponse(content=f'<script>alert("Financial year {financial_year} added successfully"); window.location.href="/dashboard";</script>')

@router.get("/{company_id}")
async def view_company(
    company_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    companies_collection = await get_collection("companies")
    company = await companies_collection.find_one({"_id": ObjectId(company_id)})
    
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    return templates.TemplateResponse("companies/view.html", {
        "request": request,
        "current_user": current_user,
        "company": company
    })