from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, JSONResponse
from datetime import datetime
from bson import ObjectId
from typing import Optional, List

from app.dependencies import get_current_user, get_current_company, get_template_context, get_company_filter
from app.database import get_collection
from app.services.audit_service import AuditService

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("")
async def list_payments(
    context: dict = Depends(get_template_context)
):
    payments_collection = await get_collection("payments")
    
    all_payments = await payments_collection.find(
        get_company_filter(context["current_company"])
    ).sort("payment_date", -1).to_list(None)
    
    sales_receipts = [p for p in all_payments if p.get("payment_type") == "receipt"]
    purchase_payments = [p for p in all_payments if p.get("payment_type") != "receipt"]
    
    context.update({
        "sales_receipts": sales_receipts,
        "purchase_payments": purchase_payments,
        "breadcrumbs": [
            {"name": "Dashboard", "url": "/dashboard"},
            {"name": "Payments", "url": "/payments"}
        ]
    })
    return templates.TemplateResponse("payments/list.html", context)

@router.get("/api/customer-invoices/{customer_id}")
async def get_customer_invoices(
    customer_id: str,
    current_company: dict = Depends(get_current_company)
):
    invoices_collection = await get_collection("sales_invoices")
    payments_collection = await get_collection("payments")
    
    invoices = await invoices_collection.find({
        "company_id": ObjectId(current_company["_id"]),
        "customer_id": ObjectId(customer_id)
    }).sort("invoice_date", -1).to_list(None)
    
    result = []
    for inv in invoices:
        existing_payments = await payments_collection.find({"invoices.invoice_id": inv["_id"]}).to_list(None)
        total_paid = sum(
            item["amount"] for p in existing_payments 
            for item in p.get("invoices", []) 
            if item["invoice_id"] == inv["_id"]
        )
        
        # Calculate interest if overdue
        interest = 0
        if inv.get("due_date") and inv.get("interest_rate", 0) > 0:
            due_date = inv["due_date"]
            today = datetime.now()
            if today > due_date:
                overdue_days = (today - due_date).days
                interest = (inv["total_amount"] * inv["interest_rate"] * overdue_days) / (365 * 100)
        
        outstanding = inv["total_amount"] - total_paid
        
        if outstanding > 0:
            result.append({
                "id": str(inv["_id"]),
                "invoice_no": inv["invoice_no"],
                "invoice_date": inv["invoice_date"].strftime("%Y-%m-%d"),
                "total_amount": inv["total_amount"],
                "interest": interest,
                "total_paid": total_paid,
                "outstanding": outstanding
            })
    
    return JSONResponse(content=result)

@router.get("/api/supplier-invoices/{supplier_id}")
async def get_supplier_invoices(
    supplier_id: str,
    current_company: dict = Depends(get_current_company)
):
    challans_collection = await get_collection("purchase_challans")
    payments_collection = await get_collection("payments")
    
    challans = await challans_collection.find({
        "company_id": ObjectId(current_company["_id"]),
        "supplier_id": ObjectId(supplier_id),
        "status": "finalized",
        "payment_status": {"$ne": "completed"}
    }).sort("challan_date", -1).to_list(None)
    
    result = []
    for c in challans:
        total_kg = sum(item.get("quantity", 0) for item in c.get("items", []))
        total_carton = len(c.get("items", []))
        
        existing_payments = await payments_collection.find({"invoices.challan_id": c["_id"]}).to_list(None)
        total_paid = sum(
            inv["amount"] for p in existing_payments 
            for inv in p.get("invoices", []) 
            if inv["challan_id"] == c["_id"]
        )
        outstanding = c["total_amount"] - total_paid
        
        result.append({
            "id": str(c["_id"]),
            "invoice_no": c.get("invoice_no", ""),
            "challan_no": c.get("challan_no", ""),
            "invoice_date": c["challan_date"].strftime("%Y-%m-%d"),
            "total_kg": total_kg,
            "total_carton": total_carton,
            "quality": c.get("items", [])[0].get("quality", "") if c.get("items") else "",
            "net_rs": c["total_amount"],
            "rate_per_kg": c["total_amount"] / total_kg if total_kg > 0 else 0,
            "total_paid": total_paid,
            "outstanding": outstanding
        })
    
    return JSONResponse(content=result)

@router.get("/sales-receipt/create")
async def create_sales_receipt_form(
    request: Request,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company)
):
    parties_collection = await get_collection("parties")
    bank_collection = await get_collection("bank_accounts")
    
    # Get customers
    customers = await parties_collection.find({
        "company_id": ObjectId(current_company["_id"]),
        "party_type": {"$in": ["customer", "both"]}
    }).sort("name", 1).to_list(None)
    
    # Get bank accounts
    banks = await bank_collection.find({
        "company_id": ObjectId(current_company["_id"]),
        "is_active": True
    }).to_list(None)
    
    return templates.TemplateResponse("payments/create_sales_receipt.html", {
        "request": request,
        "current_user": current_user,
        "current_company": current_company,
        "customers": customers,
        "banks": banks,
        "breadcrumbs": [
            {"name": "Dashboard", "url": "/dashboard"},
            {"name": "Payments", "url": "/payments"},
            {"name": "Receipt Entry", "url": "/payments/sales-receipt/create"}
        ]
    })

@router.get("/receipt/create")
async def create_receipt_form(
    request: Request,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company)
):
    parties_collection = await get_collection("parties")
    bank_collection = await get_collection("bank_accounts")
    
    # Get suppliers
    suppliers = await parties_collection.find({
        "company_id": ObjectId(current_company["_id"]),
        "party_type": {"$in": ["supplier", "both"]}
    }).sort("name", 1).to_list(None)
    
    # Get bank accounts
    banks = await bank_collection.find({
        "company_id": ObjectId(current_company["_id"]),
        "is_active": True
    }).to_list(None)
    
    # Convert ObjectId and datetime to string for JSON serialization
    for bank in banks:
        bank["_id"] = str(bank["_id"])
        bank["company_id"] = str(bank["company_id"])
        if "created_at" in bank:
            bank["created_at"] = bank["created_at"].isoformat() if bank["created_at"] else None
        if "updated_at" in bank:
            bank["updated_at"] = bank["updated_at"].isoformat() if bank["updated_at"] else None
    
    for supplier in suppliers:
        supplier["_id"] = str(supplier["_id"])
        supplier["company_id"] = str(supplier["company_id"])
        if "created_at" in supplier:
            supplier["created_at"] = supplier["created_at"].isoformat() if supplier["created_at"] else None
        if "updated_at" in supplier:
            supplier["updated_at"] = supplier["updated_at"].isoformat() if supplier["updated_at"] else None
    
    return templates.TemplateResponse("payments/create_receipt.html", {
        "request": request,
        "current_user": current_user,
        "current_company": current_company,
        "suppliers": suppliers,
        "banks": banks,
        "breadcrumbs": [
            {"name": "Dashboard", "url": "/dashboard"},
            {"name": "Payments", "url": "/payments"},
            {"name": "Payment Entry", "url": "/payments/receipt/create"}
        ]
    })

@router.post("/sales-receipt/create")
async def create_sales_receipt(
    request: Request,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company)
):
    import json
    form_data = await request.form()
    payments_collection = await get_collection("payments")
    invoices_collection = await get_collection("sales_invoices")
    parties_collection = await get_collection("parties")
    bank_transactions_collection = await get_collection("bank_transactions")
    
    customer_id = form_data.get("customer_id")
    customer = await parties_collection.find_one({"_id": ObjectId(customer_id)})
    
    count = await payments_collection.count_documents({"company_id": ObjectId(current_company["_id"])})
    payment_no = f"REC{count + 1:04d}"
    
    selected_invoices = json.loads(form_data.get("selected_invoices", "[]"))
    invoice_details = []
    for inv_data in selected_invoices:
        invoice = await invoices_collection.find_one({"_id": ObjectId(inv_data["invoice_id"])})
        if invoice:
            invoice_details.append({
                "invoice_id": ObjectId(inv_data["invoice_id"]),
                "invoice_no": invoice["invoice_no"],
                "amount": float(inv_data["amount"])
            })
    
    payment_data = {
        "company_id": ObjectId(current_company["_id"]),
        "financial_year": current_company.get("financial_year"),
        "payment_no": payment_no,
        "payment_date": datetime.fromisoformat(form_data.get("payment_date")),
        "payment_type": "receipt",
        "party_id": ObjectId(customer_id),
        "party_name": customer["name"],
        "invoices": invoice_details,
        "cheque_amount": float(form_data.get("cheque_amount", 0)),
        "amount_disburse": float(form_data.get("amount_disburse", 0)),
        "balance_amount": float(form_data.get("balance_amount", 0)),
        "outstanding": float(form_data.get("outstanding", 0)),
        "kasar": float(form_data.get("kasar", 0)),
        "interest": float(form_data.get("interest", 0)),
        "bank_name": form_data.get("bank_name"),
        "cheque_no": form_data.get("cheque_no"),
        "rr": form_data.get("rr"),
        "effect_on_passbook": form_data.get("effect_on_passbook") == "Y",
        "created_by": ObjectId(current_user["_id"]),
        "created_at": datetime.utcnow()
    }
    
    result = await payments_collection.insert_one(payment_data)
    
    # Update invoice payment status
    for inv_data in selected_invoices:
        invoice_id = ObjectId(inv_data["invoice_id"])
        payment_amount = float(inv_data["amount"])
        
        invoice = await invoices_collection.find_one({"_id": invoice_id})
        if invoice:
            # Calculate total paid for this invoice
            existing_payments = await payments_collection.find({"invoices.invoice_id": invoice_id}).to_list(None)
            total_paid = sum(
                item["amount"] for p in existing_payments 
                for item in p.get("invoices", []) 
                if item["invoice_id"] == invoice_id
            )
            
            # Calculate interest on remaining balance if overdue
            balance = invoice["total_amount"] - total_paid
            interest = 0
            if balance > 0 and invoice.get("due_date") and invoice.get("interest_rate", 0) > 0:
                due_date = invoice["due_date"]
                today = datetime.now()
                if today > due_date:
                    overdue_days = (today - due_date).days
                    interest = (balance * invoice["interest_rate"] * overdue_days) / (365 * 100)
            
            outstanding = balance
            
            # Determine payment status
            if outstanding <= 0.01:  # Allow small rounding differences
                payment_status = "paid"
            elif total_paid > 0:
                payment_status = "partial"
            else:
                payment_status = "unpaid"
            
            # Update invoice
            await invoices_collection.update_one(
                {"_id": invoice_id},
                {"$set": {
                    "total_paid": total_paid,
                    "outstanding": outstanding,
                    "payment_status": payment_status,
                    "updated_at": datetime.utcnow()
                }}
            )
    
    # Create bank passbook entry if effect on passbook is Y
    if form_data.get("effect_on_passbook") == "Y" and form_data.get("bank_name"):
        bank_accounts_collection = await get_collection("bank_accounts")
        bank = await bank_accounts_collection.find_one({
            "company_id": ObjectId(current_company["_id"]),
            "bank_name": form_data.get("bank_name")
        })
        
        if bank:
            await bank_transactions_collection.insert_one({
                "company_id": ObjectId(current_company["_id"]),
                "financial_year": current_company.get("financial_year"),
                "bank_account_id": bank["_id"],
                "transaction_date": datetime.fromisoformat(form_data.get("payment_date")),
                "transaction_type": "credit",
                "amount": float(form_data.get("cheque_amount", 0)),
                "reference_type": "payment_receipt",
                "reference_id": result.inserted_id,
                "reference_no": payment_no,
                "party_name": customer["name"],
                "cheque_no": form_data.get("cheque_no"),
                "description": f"Payment received from {customer['name']}",
                "created_by": ObjectId(current_user["_id"]),
                "created_at": datetime.utcnow()
            })
    
    return RedirectResponse(url="/payments", status_code=303)

@router.post("/receipt/create")
async def create_receipt(
    request: Request,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company)
):
    import json
    try:
        form_data = await request.form()
        payments_collection = await get_collection("payments")
        challans_collection = await get_collection("purchase_challans")
        parties_collection = await get_collection("parties")
        
        supplier_id = form_data.get("supplier_id")
        if not supplier_id:
            raise HTTPException(status_code=400, detail="Supplier not selected")
        
        selected_invoices_json = form_data.get("selected_invoices")
        if not selected_invoices_json:
            raise HTTPException(status_code=400, detail="No invoices selected")
        
        selected_invoices = json.loads(selected_invoices_json)
        if not selected_invoices:
            raise HTTPException(status_code=400, detail="No invoices selected")
        
        supplier = await parties_collection.find_one({"_id": ObjectId(supplier_id)})
        if not supplier:
            raise HTTPException(status_code=404, detail="Supplier not found")
        
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid invoice data")
    except Exception as e:
        print(f"Error in create_receipt: {str(e)}")
        raise
    
    total_amount = float(form_data.get("amount") or 0)
    total_disbursement = sum(float(inv["amount"]) for inv in selected_invoices)
    
    count = await payments_collection.count_documents({"company_id": ObjectId(current_company["_id"])})
    payment_no = f"PAY{count + 1:04d}"
    
    invoice_details = []
    for inv_data in selected_invoices:
        challan = await challans_collection.find_one({"_id": ObjectId(inv_data["invoice_id"])})
        if challan:
            invoice_details.append({
                "challan_id": ObjectId(inv_data["invoice_id"]),
                "invoice_no": challan["invoice_no"],
                "challan_no": challan["challan_no"],
                "amount": float(inv_data["amount"])
            })
    
    payment_data = {
        "company_id": ObjectId(current_company["_id"]),
        "financial_year": current_company.get("financial_year"),
        "payment_no": payment_no,
        "payment_date": datetime.fromisoformat(form_data.get("payment_date")),
        "payment_type": form_data.get("payment_type", "cheque"),
        "supplier_id": ObjectId(supplier_id),
        "supplier_name": supplier["name"],
        "invoices": invoice_details,
        "amount": total_amount,
        "bank_name": form_data.get("bank_name"),
        "cheque_no": form_data.get("cheque_no") if form_data.get("payment_type") == "cheque" else None,
        "rr": form_data.get("rr"),
        "effect_on_passbook": form_data.get("effect_on_passbook") == "yes",
        "cheque_amount": float(form_data.get("cheque_amount") or 0),
        "disbursement": total_disbursement,
        "balance_amount": float(form_data.get("balance_amount") or 0),
        "kasar": float(form_data.get("kasar") or 0),
        "interest": float(form_data.get("interest") or 0),
        "created_by": ObjectId(current_user["_id"]),
        "created_at": datetime.utcnow()
    }
    
    try:
        result = await payments_collection.insert_one(payment_data)
        
        if result.inserted_id:
            for inv_data in selected_invoices:
                challan_id = ObjectId(inv_data["invoice_id"])
                payment_amount = float(inv_data["amount"])
                
                challan = await challans_collection.find_one({"_id": challan_id})
                if challan:
                    existing_payments = await payments_collection.find({"invoices.challan_id": challan_id}).to_list(None)
                    total_paid = sum(
                        inv["amount"] for p in existing_payments 
                        for inv in p.get("invoices", []) 
                        if inv["challan_id"] == challan_id
                    )
                    
                    final_rs = challan["total_amount"]
                    payment_status = "completed" if total_paid >= final_rs else "partial"
                    
                    await challans_collection.update_one(
                        {"_id": challan_id},
                        {"$set": {
                            "total_paid": total_paid,
                            "outstanding": final_rs - total_paid,
                            "payment_status": payment_status,
                            "updated_at": datetime.utcnow()
                        }}
                    )
            
            # Create bank passbook entry if effect on passbook is yes
            if form_data.get("effect_on_passbook") == "yes" and form_data.get("bank_name"):
                bank_accounts_collection = await get_collection("bank_accounts")
                bank_transactions_collection = await get_collection("bank_transactions")
                bank = await bank_accounts_collection.find_one({
                    "company_id": ObjectId(current_company["_id"]),
                    "bank_name": form_data.get("bank_name")
                })
                
                if bank:
                    await bank_transactions_collection.insert_one({
                        "company_id": ObjectId(current_company["_id"]),
                        "financial_year": current_company.get("financial_year"),
                        "bank_account_id": bank["_id"],
                        "transaction_date": datetime.fromisoformat(form_data.get("payment_date")),
                        "transaction_type": "debit",
                        "amount": float(form_data.get("cheque_amount") or form_data.get("amount") or 0),
                        "reference_type": "payment_made",
                        "reference_id": result.inserted_id,
                        "reference_no": payment_no,
                        "supplier_name": supplier["name"],
                        "cheque_no": form_data.get("cheque_no"),
                        "description": f"Payment made to {supplier['name']}",
                        "created_by": ObjectId(current_user["_id"]),
                        "created_at": datetime.utcnow()
                    })
            
            return RedirectResponse(url=f"/payments/{result.inserted_id}", status_code=303)
        else:
            raise HTTPException(status_code=500, detail="Failed to create payment")
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error creating payment: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@router.get("/{payment_id}")
async def view_payment(
    payment_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company)
):
    payments_collection = await get_collection("payments")
    parties_collection = await get_collection("parties")
    
    payment = await payments_collection.find_one({
        "_id": ObjectId(payment_id),
        "company_id": ObjectId(current_company["_id"])
    })
    
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    
    party = None
    if payment.get("supplier_id"):
        party = await parties_collection.find_one({"_id": payment["supplier_id"]})
    elif payment.get("party_id"):
        party = await parties_collection.find_one({"_id": payment["party_id"]})
    
    if payment.get("payment_type") == "receipt":
        # Sales receipt - load invoice details
        invoices_collection = await get_collection("sales_invoices")
        for inv in payment.get("invoices", []):
            if "invoice_id" in inv:
                invoice = await invoices_collection.find_one({"_id": inv["invoice_id"]})
                if invoice:
                    inv["invoice_details"] = invoice
    else:
        # Purchase payment - load challan details
        challans_collection = await get_collection("purchase_challans")
        for inv in payment.get("invoices", []):
            if "challan_id" in inv:
                challan = await challans_collection.find_one({"_id": inv["challan_id"]})
                if challan:
                    inv["challan_details"] = challan
    
    return templates.TemplateResponse("payments/view.html", {
        "request": request,
        "current_user": current_user,
        "current_company": current_company,
        "payment": payment,
        "party": party,
        "breadcrumbs": [
            {"name": "Dashboard", "url": "/dashboard"},
            {"name": "Payments", "url": "/payments"},
            {"name": payment["payment_no"], "url": f"/payments/{payment_id}"}
        ]
    })

@router.get("/{payment_id}/edit")
async def edit_payment_form(
    payment_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company)
):
    payments_collection = await get_collection("payments")
    
    payment = await payments_collection.find_one({
        "_id": ObjectId(payment_id),
        "company_id": ObjectId(current_company["_id"])
    })
    
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    
    return templates.TemplateResponse("payments/edit.html", {
        "request": request,
        "current_user": current_user,
        "current_company": current_company,
        "payment": payment
    })

@router.post("/{payment_id}/edit")
async def edit_payment(
    payment_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company)
):
    form_data = await request.form()
    payments_collection = await get_collection("payments")
    
    result = await payments_collection.update_one(
        {"_id": ObjectId(payment_id), "company_id": ObjectId(current_company["_id"])},
        {"$set": {
            "amount": float(form_data.get("amount") or 0),
            "disbursement": float(form_data.get("disbursement") or 0),
            "notes_rs": float(form_data.get("notes_rs") or 0),
            "bank_name": form_data.get("bank_name"),
            "cheque_no": form_data.get("cheque_no"),
            "rr": form_data.get("rr"),
            "kasar": float(form_data.get("kasar") or 0),
            "interest": float(form_data.get("interest") or 0),
            "updated_at": datetime.utcnow()
        }}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Payment not found")
    
    return RedirectResponse(url=f"/payments/{payment_id}", status_code=303)

@router.post("/{payment_id}/delete")
async def delete_payment(
    payment_id: str,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company)
):
    payments_collection = await get_collection("payments")
    challans_collection = await get_collection("purchase_challans")
    invoices_collection = await get_collection("sales_invoices")
    bank_transactions_collection = await get_collection("bank_transactions")
    
    payment = await payments_collection.find_one({
        "_id": ObjectId(payment_id),
        "company_id": ObjectId(current_company["_id"])
    })
    
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    
    # Delete bank passbook entry if exists
    if payment.get("effect_on_passbook"):
        ref_type = "payment_receipt" if payment.get("payment_type") == "receipt" else "payment_made"
        await bank_transactions_collection.delete_one({
            "reference_type": ref_type,
            "reference_id": ObjectId(payment_id)
        })
    
    result = await payments_collection.delete_one({"_id": ObjectId(payment_id)})
    
    if result.deleted_count > 0:
        for inv in payment.get("invoices", []):
            # Handle sales receipts (invoice_id)
            if "invoice_id" in inv:
                invoice_id = inv["invoice_id"]
                existing_payments = await payments_collection.find({"invoices.invoice_id": invoice_id}).to_list(None)
                total_paid = sum(
                    item["amount"] for p in existing_payments 
                    for item in p.get("invoices", []) 
                    if item.get("invoice_id") == invoice_id
                )
                
                invoice = await invoices_collection.find_one({"_id": invoice_id})
                if invoice:
                    outstanding = invoice["total_amount"] - total_paid
                    payment_status = "paid" if total_paid >= invoice["total_amount"] else "partial" if total_paid > 0 else "unpaid"
                    
                    await invoices_collection.update_one(
                        {"_id": invoice_id},
                        {"$set": {
                            "total_paid": total_paid,
                            "outstanding": outstanding,
                            "payment_status": payment_status,
                            "updated_at": datetime.utcnow()
                        }}
                    )
            
            # Handle purchase payments (challan_id)
            elif "challan_id" in inv:
                challan_id = inv["challan_id"]
                existing_payments = await payments_collection.find({"invoices.challan_id": challan_id}).to_list(None)
                total_paid = sum(
                    item["amount"] for p in existing_payments 
                    for item in p.get("invoices", []) 
                    if item.get("challan_id") == challan_id
                )
                
                challan = await challans_collection.find_one({"_id": challan_id})
                if challan:
                    payment_status = "completed" if total_paid >= challan["total_amount"] else "partial" if total_paid > 0 else None
                    
                    await challans_collection.update_one(
                        {"_id": challan_id},
                        {"$set": {
                            "total_paid": total_paid,
                            "outstanding": challan["total_amount"] - total_paid,
                            "payment_status": payment_status,
                            "updated_at": datetime.utcnow()
                        }}
                    )
    
    return RedirectResponse(url="/payments", status_code=302)

@router.get("/ledger/{party_id}")
async def party_ledger(
    party_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company)
):
    parties_collection = await get_collection("parties")
    payments_collection = await get_collection("payments")
    invoices_collection = await get_collection("sales_invoices")
    challans_collection = await get_collection("purchase_challans")
    
    # Get party details
    party = await parties_collection.find_one({"_id": ObjectId(party_id)})
    if not party:
        raise HTTPException(status_code=404, detail="Party not found")
    
    # Get all transactions for this party
    transactions = []
    
    # Add invoices (if customer)
    if party["party_type"] in ["customer", "both"]:
        invoices = await invoices_collection.find({
            "company_id": ObjectId(current_company["_id"]),
            "customer_id": ObjectId(party_id)
        }).sort("invoice_date", 1).to_list(None)
        
        for invoice in invoices:
            transactions.append({
                "date": invoice["invoice_date"],
                "type": "invoice",
                "reference": invoice["invoice_no"],
                "debit": invoice["total_amount"],
                "credit": 0,
                "balance": 0  # Will be calculated
            })
    
    # Add challans (if supplier)
    if party["party_type"] in ["supplier", "both"]:
        challans = await challans_collection.find({
            "company_id": ObjectId(current_company["_id"]),
            "supplier_id": ObjectId(party_id)
        }).sort("challan_date", 1).to_list(None)
        
        for challan in challans:
            transactions.append({
                "date": challan["challan_date"],
                "type": "challan",
                "reference": challan["challan_no"],
                "debit": 0,
                "credit": challan["total_amount"],
                "balance": 0
            })
    
    # Add payments
    payments = await payments_collection.find({
        "company_id": ObjectId(current_company["_id"]),
        "party_id": ObjectId(party_id)
    }).sort("payment_date", 1).to_list(None)
    
    for payment in payments:
        if payment["payment_type"] == "receipt":
            transactions.append({
                "date": payment["payment_date"],
                "type": "receipt",
                "reference": payment["payment_no"],
                "debit": 0,
                "credit": payment["net_amount"],
                "balance": 0
            })
        else:
            transactions.append({
                "date": payment["payment_date"],
                "type": "payment",
                "reference": payment["payment_no"],
                "debit": payment["net_amount"],
                "credit": 0,
                "balance": 0
            })
    
    # Sort by date and calculate running balance
    transactions.sort(key=lambda x: x["date"])
    running_balance = party["opening_balance"]
    
    for transaction in transactions:
        running_balance += transaction["debit"] - transaction["credit"]
        transaction["balance"] = running_balance
    
    return templates.TemplateResponse("payments/ledger.html", {
        "request": request,
        "current_user": current_user,
        "current_company": current_company,
        "party": party,
        "transactions": transactions,
        "breadcrumbs": [
            {"name": "Dashboard", "url": "/dashboard"},
            {"name": "Parties", "url": "/parties"},
            {"name": f"{party['name']} Ledger", "url": f"/payments/ledger/{party_id}"}
        ]
    })