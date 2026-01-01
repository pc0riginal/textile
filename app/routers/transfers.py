from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, JSONResponse
from datetime import datetime
from bson import ObjectId
from typing import List

from app.dependencies import get_current_user, get_current_company, get_company_filter, get_template_context
from app.database import get_collection
from app.services.inventory_service import InventoryService

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("")
async def list_transfers(
    context: dict = Depends(get_template_context)
):
    transfers_collection = await get_collection("inventory_transfers")
    
    transfers = await transfers_collection.find(
        get_company_filter(context["current_company"])
    ).sort("transfer_date", -1).to_list(None)
    
    context.update({
        "transfers": transfers,
        "breadcrumbs": [
            {"name": "Dashboard", "url": "/dashboard"},
            {"name": "Inventory Transfers", "url": "/transfers"}
        ]
    })
    return templates.TemplateResponse("transfers/list.html", context)

@router.get("/create")
async def create_transfer_form(
    request: Request,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company)
):
    # Get available challans with inventory
    challans_collection = await get_collection("purchase_challans")
    base_filter = get_company_filter(current_company)
    available_challans = await challans_collection.find({
        **base_filter,
        "status": "finalized"
    }).sort("challan_date", -1).to_list(None)
    
    # Get parties for recipients
    parties_collection = await get_collection("parties")
    parties = await parties_collection.find(
        base_filter
    ).sort("name", 1).to_list(None)
    
    return templates.TemplateResponse("transfers/create.html", {
        "request": request,
        "current_user": current_user,
        "current_company": current_company,
        "available_challans": available_challans,
        "parties": parties,
        "breadcrumbs": [
            {"name": "Dashboard", "url": "/dashboard"},
            {"name": "Inventory Transfers", "url": "/transfers"},
            {"name": "Create", "url": "/transfers/create"}
        ]
    })

@router.post("/create")
async def create_transfer(
    request: Request,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company)
):
    form_data = await request.form()
    transfers_collection = await get_collection("inventory_transfers")
    parties_collection = await get_collection("parties")
    challans_collection = await get_collection("purchase_challans")
    
    source_challan_id = form_data.get("source_challan_id")
    source_challan = await challans_collection.find_one({"_id": ObjectId(source_challan_id)})
    if not source_challan:
        raise HTTPException(status_code=404, detail="Source challan not found")
    
    # Parse recipients
    recipients = []
    i = 0
    while f"recipients[{i}][party_id]" in form_data:
        party_id = form_data.get(f"recipients[{i}][party_id]")
        party = await parties_collection.find_one({"_id": ObjectId(party_id)})
        if party:
            recipients.append({
                "party_id": party_id,
                "party_name": party["name"],
                "quantity": float(form_data.get(f"recipients[{i}][quantity]", 0))
            })
        i += 1
    
    total_quantity = sum(r["quantity"] for r in recipients)
    
    transfer_data = {
        **get_company_filter(current_company),
        "source_challan_id": ObjectId(source_challan_id),
        "source_challan_no": source_challan["challan_no"],
        "transfer_date": datetime.fromisoformat(form_data.get("transfer_date")),
        "quantity_transferred": total_quantity,
        "recipients": recipients,
        "reason": form_data.get("reason"),
        "notes": form_data.get("notes"),
        "created_by": ObjectId(current_user["_id"]),
        "created_at": datetime.utcnow()
    }
    
    await transfers_collection.insert_one(transfer_data)
    return RedirectResponse(url="/transfers", status_code=302)

@router.get("/tracking")
async def transfer_tracking(
    request: Request,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company)
):
    # Get all transfers with their lineage
    transfers_collection = await get_collection("inventory_transfers")
    challans_collection = await get_collection("purchase_challans")
    
    transfers = await transfers_collection.find(
        get_company_filter(current_company)
    ).sort("transfer_date", -1).to_list(None)
    
    # Build transfer chains
    transfer_chains = []
    for transfer in transfers:
        # Get source challan
        source_challan = await challans_collection.find_one(
            {"_id": ObjectId(transfer["source_challan_id"])}
        )
        
        chain = {
            "transfer": transfer,
            "source_challan": source_challan,
            "recipients": []
        }
        
        # Get recipient challans
        for recipient in transfer["recipients"]:
            if recipient.get("created_challan_id"):
                recipient_challan = await challans_collection.find_one(
                    {"_id": ObjectId(recipient["created_challan_id"])}
                )
                chain["recipients"].append({
                    "party": recipient,
                    "challan": recipient_challan
                })
        
        transfer_chains.append(chain)
    
    return templates.TemplateResponse("transfers/tracking.html", {
        "request": request,
        "current_user": current_user,
        "current_company": current_company,
        "transfer_chains": transfer_chains,
        "breadcrumbs": [
            {"name": "Dashboard", "url": "/dashboard"},
            {"name": "Inventory Transfers", "url": "/transfers"},
            {"name": "Tracking", "url": "/transfers/tracking"}
        ]
    })

@router.get("/lineage/{challan_id}")
async def material_lineage(
    challan_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company)
):
    # Show complete material lineage for a challan
    challans_collection = await get_collection("purchase_challans")
    transfers_collection = await get_collection("inventory_transfers")
    
    challan = await challans_collection.find_one({"_id": ObjectId(challan_id)})
    if not challan:
        raise HTTPException(status_code=404, detail="Challan not found")
    
    lineage = {
        "challan": challan,
        "source_chain": [],
        "destination_chain": []
    }
    
    # If this challan was received via transfer, trace back to original
    if challan.get("is_received_via_transfer") and challan.get("transfer_source_id"):
        source_challan = await challans_collection.find_one(
            {"_id": ObjectId(challan["transfer_source_id"])}
        )
        lineage["source_chain"].append(source_challan)
    
    # Find all transfers from this challan
    outgoing_transfers = await transfers_collection.find(
        {"source_challan_id": ObjectId(challan_id)}
    ).to_list(None)
    
    for transfer in outgoing_transfers:
        for recipient in transfer["recipients"]:
            if recipient.get("created_challan_id"):
                recipient_challan = await challans_collection.find_one(
                    {"_id": ObjectId(recipient["created_challan_id"])}
                )
                lineage["destination_chain"].append({
                    "transfer": transfer,
                    "challan": recipient_challan
                })
    
    return templates.TemplateResponse("transfers/lineage.html", {
        "request": request,
        "current_user": current_user,
        "current_company": current_company,
        "lineage": lineage,
        "breadcrumbs": [
            {"name": "Dashboard", "url": "/dashboard"},
            {"name": "Inventory Transfers", "url": "/transfers"},
            {"name": "Material Lineage", "url": f"/transfers/lineage/{challan_id}"}
        ]
    })