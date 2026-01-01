from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from bson import ObjectId
from datetime import datetime
from app.dependencies import get_current_user, get_current_company, get_template_context
from app.database import get_collection
from app.logger import logger

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/create", response_class=HTMLResponse)
async def banking_create_form(context: dict = Depends(get_template_context)):
    return templates.TemplateResponse("banking/create.html", context)

@router.post("/create")
async def banking_create(
    request: Request,
    account_name: str = Form(...),
    account_number: str = Form(...),
    bank_name: str = Form(...),
    branch: str = Form(""),
    ifsc_code: str = Form(...),
    account_type: str = Form("Current"),
    opening_balance: float = Form(0.0),
    current_user: dict = Depends(get_current_user)
):
    current_company = await get_current_company(request, current_user)
    collection = await get_collection("bank_accounts")
    
    bank_account = {
        "account_name": account_name,
        "account_number": account_number,
        "bank_name": bank_name,
        "branch": branch,
        "ifsc_code": ifsc_code,
        "account_type": account_type,
        "opening_balance": opening_balance,
        "current_balance": opening_balance,
        "is_active": True,
        "company_id": current_company["_id"],
        "created_by": current_user.get("username"),
        "created_at": datetime.utcnow()
    }
    
    await collection.insert_one(bank_account)
    return RedirectResponse(url="/banking/banks", status_code=303)

@router.post("/api/create")
async def banking_api_create(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    current_company = await get_current_company(request, current_user)
    data = await request.json()
    collection = await get_collection("bank_accounts")
    
    bank_account = {
        "account_name": data["account_name"],
        "account_number": data["account_number"],
        "bank_name": data["bank_name"],
        "branch": data.get("branch", ""),
        "ifsc_code": data["ifsc_code"],
        "account_type": data.get("account_type", "Current"),
        "opening_balance": data.get("opening_balance", 0.0),
        "current_balance": data.get("opening_balance", 0.0),
        "is_active": True,
        "company_id": current_company["_id"],
        "created_by": current_user.get("username"),
        "created_at": datetime.utcnow()
    }
    
    result = await collection.insert_one(bank_account)
    return JSONResponse(content={"id": str(result.inserted_id), "bank_name": data["bank_name"], "account_number": data["account_number"]})

@router.get("/passbook")
async def passbook(context: dict = Depends(get_template_context), bank_id: str = None):
    current_company = context["current_company"]
    bank_collection = await get_collection("bank_accounts")
    payments_collection = await get_collection("payments")
    
    banks = await bank_collection.find({"company_id": ObjectId(current_company["_id"]) if isinstance(current_company["_id"], str) else current_company["_id"]}).to_list(None)
    
    transactions = []
    selected_bank = None
    
    if bank_id:
        selected_bank = await bank_collection.find_one({"_id": ObjectId(bank_id), "company_id": current_company["_id"]})
        
        if selected_bank:
            payments = await payments_collection.find({
                "company_id": current_company["_id"],
                "$or": [
                    {"bank_name": selected_bank["bank_name"]},
                    {"bank_name": selected_bank["account_name"]}
                ],
                "effect_on_passbook": True
            }).sort("payment_date", 1).to_list(None)
            
            running_balance = selected_bank.get("opening_balance", 0)
            
            for payment in payments:
                party_name = payment.get("party_name") or payment.get("supplier_name", "Unknown")
                payment_type = payment.get("payment_type", "payment")
                
                invoice_nos = ", ".join([inv.get("invoice_no", "") for inv in payment.get("invoices", [])]) if payment.get("invoices") else payment.get("invoice_no", "")
                
                if payment_type == "receipt":
                    # Credit for sales receipt
                    running_balance += payment.get("cheque_amount", 0)
                    transactions.append({
                        "date": payment["payment_date"],
                        "description": f"Payment received from {party_name} - {invoice_nos}",
                        "cheque_no": payment.get("cheque_no") or payment.get("rr") or "-",
                        "debit": 0,
                        "credit": payment.get("cheque_amount", 0),
                        "balance": running_balance
                    })
                else:
                    # Debit for purchase payment
                    running_balance -= payment.get("cheque_amount", 0)
                    transactions.append({
                        "date": payment["payment_date"],
                        "description": f"Payment to {party_name} - {invoice_nos}",
                        "cheque_no": payment.get("cheque_no") or payment.get("rr") or "-",
                        "debit": payment.get("cheque_amount", 0),
                        "credit": 0,
                        "balance": running_balance
                    })
    
    context.update({
        "banks": banks,
        "selected_bank": selected_bank,
        "transactions": transactions,
        "bank_id": str(bank_id) if bank_id else None
    })
    return templates.TemplateResponse("banking/passbook.html", context)

@router.get("/{bank_id}/edit", response_class=HTMLResponse)
async def banking_edit_form(bank_id: str, context: dict = Depends(get_template_context)):
    collection = await get_collection("bank_accounts")
    
    bank = await collection.find_one({"_id": ObjectId(bank_id), "company_id": context["current_company"]["_id"]})
    if not bank:
        raise HTTPException(status_code=404, detail="Bank account not found")
    
    context["bank"] = bank
    return templates.TemplateResponse("banking/edit.html", context)

@router.post("/{bank_id}/edit")
async def banking_edit(
    bank_id: str,
    request: Request,
    account_name: str = Form(...),
    account_number: str = Form(...),
    bank_name: str = Form(...),
    branch: str = Form(""),
    ifsc_code: str = Form(...),
    account_type: str = Form("Current"),
    current_user: dict = Depends(get_current_user)
):
    current_company = await get_current_company(request, current_user)
    collection = await get_collection("bank_accounts")
    
    result = await collection.update_one(
        {"_id": ObjectId(bank_id), "company_id": current_company["_id"]},
        {"$set": {
            "account_name": account_name,
            "account_number": account_number,
            "bank_name": bank_name,
            "branch": branch,
            "ifsc_code": ifsc_code,
            "account_type": account_type,
            "updated_at": datetime.utcnow()
        }}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Bank account not found")
    
    return RedirectResponse(url="/banking/banks", status_code=303)

@router.post("/{bank_id}/delete")
async def banking_delete(bank_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    current_company = await get_current_company(request, current_user)
    collection = await get_collection("bank_accounts")
    
    result = await collection.delete_one({"_id": ObjectId(bank_id), "company_id": current_company["_id"]})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Bank account not found")
    
    return RedirectResponse(url="/banking/banks", status_code=303)

@router.get("/banks", response_class=HTMLResponse)
async def banking_list(context: dict = Depends(get_template_context)):
    collection = await get_collection("bank_accounts")
    
    company_id = ObjectId(context["current_company"]["_id"]) if isinstance(context["current_company"]["_id"], str) else context["current_company"]["_id"]
    banks = await collection.find({"company_id": company_id}).to_list(None)
    
    if len(banks) == 0:
        banks = await collection.find({"company_id": str(company_id)}).to_list(None)
    
    context["banks"] = banks
    return templates.TemplateResponse("banking/index.html", context)

@router.get("/view/{bank_id}", response_class=HTMLResponse)
async def banking_view(bank_id: str, context: dict = Depends(get_template_context)):
    collection = await get_collection("bank_accounts")
    
    bank = await collection.find_one({"_id": ObjectId(bank_id), "company_id": context["current_company"]["_id"]})
    if not bank:
        raise HTTPException(status_code=404, detail="Bank account not found")
    
    context["bank"] = bank
    return templates.TemplateResponse("banking/view.html", context)
