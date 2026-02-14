from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from bson import ObjectId
from datetime import datetime
from app import TEMPLATES_DIR
from app.dependencies import get_current_user, get_current_company, get_template_context
from app.database import get_collection
from app.utils import number_to_words
from app.logger import logger

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)


# ── Financial Year Helpers ─────────────────────────────────────────

def get_fy_date_range(financial_year: str):
    """Parse '2025-2026' into (datetime(2025,4,1), datetime(2026,3,31,23,59,59))"""
    try:
        start_year, end_year = map(int, financial_year.split("-"))
        fy_start = datetime(start_year, 4, 1)
        fy_end = datetime(end_year, 3, 31, 23, 59, 59)
        return fy_start, fy_end
    except Exception:
        return None, None


async def get_fy_opening_balance(bank_id, company_id, financial_year: str, bank_doc: dict = None):
    """Get the opening balance for a specific FY. Falls back to bank's opening_balance."""
    fy_col = await get_collection("bank_fy_balances")
    fy_rec = await fy_col.find_one({
        "bank_id": ObjectId(bank_id) if isinstance(bank_id, str) else bank_id,
        "company_id": company_id,
        "financial_year": financial_year,
    })
    if fy_rec:
        return fy_rec.get("opening_balance", 0.0)
    # Fallback: use bank's original opening_balance
    if not bank_doc:
        bank_col = await get_collection("bank_accounts")
        bank_doc = await bank_col.find_one({"_id": ObjectId(bank_id) if isinstance(bank_id, str) else bank_id})
    return bank_doc.get("opening_balance", 0.0) if bank_doc else 0.0


# ── Cheque Number Helper ───────────────────────────────────────────

async def get_next_cheque_no(bank_id: str, company_id, bank_doc: dict = None) -> int | None:
    """
    Get the next cheque number for a bank account by finding the highest
    numeric cheque_no used across passbook_entries AND payments, then +1.
    Falls back to bank.next_cheque_no if no cheques exist yet.
    """
    if not bank_doc:
        bank_collection = await get_collection("bank_accounts")
        bank_doc = await bank_collection.find_one({"_id": ObjectId(bank_id)})
        if not bank_doc:
            return None

    max_cheque = 0

    # 1) Max from passbook_entries for this bank
    entries_col = await get_collection("passbook_entries")
    pipeline = [
        {"$match": {"bank_id": ObjectId(bank_id), "company_id": company_id, "cheque_no": {"$exists": True, "$ne": ""}}},
        {"$addFields": {"cheque_num": {"$toInt": {"$ifNull": [{"$cond": [{"$regexMatch": {"input": "$cheque_no", "regex": "^\\d+$"}}, "$cheque_no", None]}, "0"]}}}},
        {"$group": {"_id": None, "max_no": {"$max": "$cheque_num"}}}
    ]
    result = await entries_col.aggregate(pipeline).to_list(1)
    if result and result[0].get("max_no"):
        max_cheque = max(max_cheque, result[0]["max_no"])

    # 2) Max from payments for this bank (matched by bank_name or account_name)
    payments_col = await get_collection("payments")
    bank_names = [bank_doc.get("bank_name", ""), bank_doc.get("account_name", "")]
    bank_names = [n for n in bank_names if n]
    if bank_names:
        pipeline2 = [
            {"$match": {"company_id": company_id, "bank_name": {"$in": bank_names}, "cheque_no": {"$exists": True, "$ne": None}}},
            {"$addFields": {"cheque_num": {"$toInt": {"$ifNull": [{"$cond": [{"$regexMatch": {"input": {"$toString": "$cheque_no"}, "regex": "^\\d+$"}}, {"$toString": "$cheque_no"}, None]}, "0"]}}}},
            {"$group": {"_id": None, "max_no": {"$max": "$cheque_num"}}}
        ]
        result2 = await payments_col.aggregate(pipeline2).to_list(1)
        if result2 and result2[0].get("max_no"):
            max_cheque = max(max_cheque, result2[0]["max_no"])

    # 3) Compare with bank's stored next_cheque_no (user-set starting point)
    stored_next = bank_doc.get("next_cheque_no") or 0

    if max_cheque > 0:
        next_no = max(max_cheque + 1, stored_next)
    elif stored_next > 0:
        next_no = stored_next
    else:
        return None  # No cheque sequence configured and no cheques used

    return next_no


# ── API: Next Cheque Number ────────────────────────────────────────

@router.get("/api/next-cheque")
async def api_next_cheque(
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company),
    bank_id: str = None,
    bank_name: str = None,
):
    """Returns the next cheque number for a bank account. Accepts bank_id or bank_name."""
    if not bank_id and not bank_name:
        return JSONResponse(content={"next_cheque_no": None})
    try:
        if not bank_id and bank_name:
            # Resolve bank_id from bank_name
            bank_collection = await get_collection("bank_accounts")
            bank_doc = await bank_collection.find_one({
                "company_id": current_company["_id"],
                "$or": [{"bank_name": bank_name}, {"account_name": bank_name}]
            })
            if not bank_doc:
                return JSONResponse(content={"next_cheque_no": None})
            bank_id = str(bank_doc["_id"])
        next_no = await get_next_cheque_no(bank_id, current_company["_id"])
        return JSONResponse(content={"next_cheque_no": next_no})
    except Exception:
        return JSONResponse(content={"next_cheque_no": None})


# ── Bank Account CRUD ──────────────────────────────────────────────

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
    next_cheque_no: str = Form(""),
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
        "next_cheque_no": int(next_cheque_no) if next_cheque_no.strip() else None,
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

@router.get("/banks", response_class=HTMLResponse)
async def banking_list(context: dict = Depends(get_template_context)):
    collection = await get_collection("bank_accounts")
    company_id = context["current_company"]["_id"] if isinstance(context["current_company"]["_id"], ObjectId) else ObjectId(context["current_company"]["_id"])
    banks = await collection.find({"company_id": company_id}).to_list(None)
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
    next_cheque_no: str = Form(""),
    current_user: dict = Depends(get_current_user)
):
    current_company = await get_current_company(request, current_user)
    collection = await get_collection("bank_accounts")
    update_fields = {
        "account_name": account_name,
        "account_number": account_number,
        "bank_name": bank_name,
        "branch": branch,
        "ifsc_code": ifsc_code,
        "account_type": account_type,
        "updated_at": datetime.utcnow()
    }
    if next_cheque_no.strip():
        update_fields["next_cheque_no"] = int(next_cheque_no)
    result = await collection.update_one(
        {"_id": ObjectId(bank_id), "company_id": current_company["_id"]},
        {"$set": update_fields}
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


# ── Passbook (merged: payments + direct entries) ───────────────────

@router.get("/passbook")
async def passbook(context: dict = Depends(get_template_context), bank_id: str = None):
    current_company = context["current_company"]
    financial_year = current_company.get("financial_year", "")
    fy_start, fy_end = get_fy_date_range(financial_year)
    bank_collection = await get_collection("bank_accounts")
    banks = await bank_collection.find({"company_id": current_company["_id"]}).to_list(None)

    transactions = []
    selected_bank = None
    fy_opening_balance = 0.0

    if bank_id:
        selected_bank = await bank_collection.find_one({"_id": ObjectId(bank_id), "company_id": current_company["_id"]})

        if selected_bank:
            # Get FY-specific opening balance
            fy_opening_balance = await get_fy_opening_balance(
                bank_id, current_company["_id"], financial_year, selected_bank
            )

            # Build date filter for FY
            date_filter = {}
            if fy_start and fy_end:
                date_filter = {"$gte": fy_start, "$lte": fy_end}

            # 1) Payment-based transactions
            payments_collection = await get_collection("payments")
            pay_query = {
                "company_id": current_company["_id"],
                "$or": [
                    {"bank_name": selected_bank["bank_name"]},
                    {"bank_name": selected_bank["account_name"]}
                ],
                "effect_on_passbook": True
            }
            if date_filter:
                pay_query["payment_date"] = date_filter
            payments = await payments_collection.find(pay_query).sort("payment_date", 1).to_list(None)

            for payment in payments:
                party_name = payment.get("party_name") or payment.get("supplier_name", "Unknown")
                payment_type = payment.get("payment_type", "payment")
                invoice_nos = ", ".join([inv.get("invoice_no", "") for inv in payment.get("invoices", [])]) if payment.get("invoices") else payment.get("invoice_no", "")

                if payment_type == "receipt":
                    transactions.append({
                        "date": payment["payment_date"],
                        "particulars": party_name,
                        "invoice_no": invoice_nos,
                        "cheque_no": payment.get("cheque_no") or payment.get("rr") or "-",
                        "credit": payment.get("cheque_amount", 0),
                        "debit": 0,
                        "source": "payment",
                        "source_id": str(payment["_id"]),
                    })
                else:
                    transactions.append({
                        "date": payment["payment_date"],
                        "particulars": party_name,
                        "invoice_no": invoice_nos,
                        "cheque_no": payment.get("cheque_no") or payment.get("rr") or "-",
                        "debit": payment.get("cheque_amount", 0),
                        "credit": 0,
                        "source": "payment",
                        "source_id": str(payment["_id"]),
                    })

            # 2) Direct passbook entries
            entries_collection = await get_collection("passbook_entries")
            entry_query = {
                "bank_id": ObjectId(bank_id),
                "company_id": current_company["_id"],
            }
            if date_filter:
                entry_query["date"] = date_filter
            entries = await entries_collection.find(entry_query).to_list(None)

            for entry in entries:
                transactions.append({
                    "date": entry["date"],
                    "particulars": entry.get("particulars", ""),
                    "invoice_no": entry.get("invoice_no", ""),
                    "cheque_no": entry.get("cheque_no", "-"),
                    "debit": entry.get("debit", 0),
                    "credit": entry.get("credit", 0),
                    "source": "entry",
                    "source_id": str(entry["_id"]),
                    "is_online": entry.get("is_online", True),
                    "remarks": entry.get("remarks", ""),
                })

            # Sort all by date
            transactions.sort(key=lambda t: t["date"])

            # Calculate running balance
            running_balance = fy_opening_balance
            for txn in transactions:
                running_balance += txn["credit"] - txn["debit"]
                txn["balance"] = running_balance

    context.update({
        "banks": banks,
        "selected_bank": selected_bank,
        "transactions": transactions,
        "bank_id": str(bank_id) if bank_id else None,
        "fy_opening_balance": fy_opening_balance,
        "financial_year": financial_year,
    })
    return templates.TemplateResponse("banking/passbook.html", context)


# ── Direct Passbook Entry (non-invoice transactions) ──────────────

@router.get("/entry/add")
async def passbook_entry_form(context: dict = Depends(get_template_context), bank_id: str = None):
    current_company = context["current_company"]
    bank_collection = await get_collection("bank_accounts")
    banks_raw = await bank_collection.find({"company_id": current_company["_id"]}).to_list(None)
    banks = [{"_id": str(b["_id"]), "bank_name": b.get("bank_name", ""), "account_number": b.get("account_number", "")} for b in banks_raw]

    selected_bank = None
    if bank_id:
        selected_bank = await bank_collection.find_one({"_id": ObjectId(bank_id), "company_id": current_company["_id"]})

    context.update({
        "banks": banks,
        "selected_bank": selected_bank,
        "bank_id": bank_id,
        "today": datetime.utcnow().strftime("%Y-%m-%d"),
        "breadcrumbs": [
            {"name": "Dashboard", "url": "/dashboard"},
            {"name": "Banking", "url": "/banking/banks"},
            {"name": "Add Entry", "url": "/banking/entry/add"},
        ]
    })
    return templates.TemplateResponse("banking/entry_add.html", context)

@router.post("/entry/add")
async def passbook_entry_create(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    current_company = await get_current_company(request, current_user)
    form = await request.form()

    bank_id = form.get("bank_id")
    if not bank_id:
        raise HTTPException(status_code=400, detail="Bank account is required")

    txn_type = form.get("txn_type", "debit")  # credit or debit
    amount = float(form.get("amount", 0))
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than 0")

    is_online = form.get("is_online", "Y")  # Y = online, N = cheque
    cheque_no = form.get("cheque_no", "").strip()

    # Auto-assign cheque number for offline (cheque) transactions
    if is_online == "N" and not cheque_no:
        bank_collection = await get_collection("bank_accounts")
        next_no = await get_next_cheque_no(bank_id, current_company["_id"])
        if next_no:
            cheque_no = str(next_no)
            # Update bank's stored next_cheque_no to next_no + 1
            await bank_collection.update_one(
                {"_id": ObjectId(bank_id)},
                {"$set": {"next_cheque_no": next_no + 1}}
            )

    entry = {
        "bank_id": ObjectId(bank_id),
        "company_id": current_company["_id"],
        "date": datetime.fromisoformat(form.get("date", datetime.utcnow().strftime("%Y-%m-%d"))),
        "particulars": form.get("particulars", "").strip(),
        "invoice_no": form.get("invoice_no", "").strip(),
        "cheque_no": cheque_no,
        "is_online": is_online == "Y",
        "remarks": form.get("remarks", "").strip(),
        "debit": amount if txn_type == "debit" else 0,
        "credit": amount if txn_type == "credit" else 0,
        "created_by": current_user.get("username"),
        "created_at": datetime.utcnow(),
    }

    entries_collection = await get_collection("passbook_entries")
    await entries_collection.insert_one(entry)

    # Update bank current_balance
    bank_collection = await get_collection("bank_accounts")
    balance_delta = entry["credit"] - entry["debit"]
    await bank_collection.update_one(
        {"_id": ObjectId(bank_id)},
        {"$inc": {"current_balance": balance_delta}}
    )

    # If cheque (offline), redirect to cheque print page with pre-filled data
    if is_online == "N" and cheque_no:
        from urllib.parse import urlencode
        params = urlencode({
            "bank_id": bank_id,
            "payee": entry["particulars"],
            "amount": amount,
            "date": form.get("date", ""),
            "cheque_no": cheque_no,
        })
        return RedirectResponse(url=f"/banking/cheque/print?{params}", status_code=303)

    return RedirectResponse(url=f"/banking/entry/add?bank_id={bank_id}", status_code=303)

@router.delete("/entry/{entry_id}")
async def passbook_entry_delete(
    entry_id: str,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company),
):
    entries_collection = await get_collection("passbook_entries")
    entry = await entries_collection.find_one({"_id": ObjectId(entry_id), "company_id": current_company["_id"]})
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    # Reverse the balance change
    bank_collection = await get_collection("bank_accounts")
    balance_delta = entry["debit"] - entry["credit"]  # reverse
    await bank_collection.update_one(
        {"_id": entry["bank_id"]},
        {"$inc": {"current_balance": balance_delta}}
    )

    await entries_collection.delete_one({"_id": ObjectId(entry_id)})
    return JSONResponse(content={"message": "Entry deleted"})


# ── Cheque Print ───────────────────────────────────────────────────

@router.get("/cheque/print")
async def cheque_print(
    context: dict = Depends(get_template_context),
    bank_id: str = None,
    payee: str = "",
    amount: float = 0,
    date: str = "",
    cheque_no: str = "",
):
    current_company = context["current_company"]
    bank_collection = await get_collection("bank_accounts")
    banks = await bank_collection.find({"company_id": current_company["_id"]}).to_list(None)

    selected_bank = None
    if bank_id:
        selected_bank = await bank_collection.find_one({"_id": ObjectId(bank_id), "company_id": current_company["_id"]})

    amount_words = number_to_words(amount) if amount > 0 else ""

    # Keep date in YYYY-MM-DD for <input type="date">
    cheque_date = ""
    if date:
        cheque_date = date  # Already YYYY-MM-DD from form/query param

    context.update({
        "banks": banks,
        "selected_bank": selected_bank,
        "bank_id": bank_id,
        "payee": payee,
        "amount": amount,
        "amount_words": amount_words,
        "cheque_date": cheque_date,
        "cheque_no": cheque_no,
        "breadcrumbs": [
            {"name": "Dashboard", "url": "/dashboard"},
            {"name": "Banking", "url": "/banking/banks"},
            {"name": "Print Cheque", "url": "/banking/cheque/print"},
        ]
    })
    return templates.TemplateResponse("banking/cheque_print.html", context)


# ── FY Opening Balance API ─────────────────────────────────────────

@router.get("/api/fy-balance")
async def api_get_fy_balance(
    bank_id: str,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company),
):
    """Get the opening balance for the current FY."""
    financial_year = current_company.get("financial_year", "")
    balance = await get_fy_opening_balance(bank_id, current_company["_id"], financial_year)
    return JSONResponse(content={"opening_balance": balance, "financial_year": financial_year})


@router.post("/api/fy-balance")
async def api_set_fy_balance(
    request: Request,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company),
):
    """Set/update the opening balance for a bank account in the current FY."""
    data = await request.json()
    bank_id = data.get("bank_id")
    opening_balance = float(data.get("opening_balance", 0))
    financial_year = current_company.get("financial_year", "")

    if not bank_id or not financial_year:
        raise HTTPException(status_code=400, detail="Bank ID and financial year are required")

    fy_col = await get_collection("bank_fy_balances")
    await fy_col.update_one(
        {
            "bank_id": ObjectId(bank_id),
            "company_id": current_company["_id"],
            "financial_year": financial_year,
        },
        {
            "$set": {
                "opening_balance": opening_balance,
                "updated_by": current_user.get("username"),
                "updated_at": datetime.utcnow(),
            },
            "$setOnInsert": {
                "created_by": current_user.get("username"),
                "created_at": datetime.utcnow(),
            }
        },
        upsert=True,
    )
    return JSONResponse(content={"message": "Opening balance updated", "opening_balance": opening_balance, "financial_year": financial_year})
