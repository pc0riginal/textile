from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
from datetime import datetime
from bson import ObjectId

from app import TEMPLATES_DIR
from app.database import get_collection
from app.auth import get_password_hash
from app.dependencies import get_current_user, get_admin_user
from app.services.license_service import get_max_users, get_license

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)


@router.get("")
async def users_page(
    request: Request,
    current_user: dict = Depends(get_admin_user),
):
    """User management page — admin only."""
    from app.services.license_service import check_license_status

    users_collection = await get_collection("users")
    users = await users_collection.find({}).sort("created_at", 1).to_list(None)

    max_users = await get_max_users()
    license_doc = await get_license()

    # Convert ObjectIds to strings for template
    for u in users:
        u["id"] = str(u["_id"])

    # Build minimal context (don't require company)
    companies_collection = await get_collection("companies")
    user_companies = await companies_collection.find(
        {"_id": {"$in": [ObjectId(cid) for cid in current_user.get("companies", [])]}}
    ).to_list(None)

    # Try to get current company (optional)
    current_company = None
    company_id = request.cookies.get("current_company_id")
    if company_id:
        try:
            current_company = await companies_collection.find_one({"_id": ObjectId(company_id)})
        except Exception:
            pass
    if not current_company and user_companies:
        current_company = user_companies[0]

    financial_years = []
    if current_company:
        financial_years = current_company.get("financial_years", [])
        if not financial_years and current_company.get("financial_year"):
            financial_years = [current_company.get("financial_year")]

    license_status = await check_license_status()

    context = {
        "request": request,
        "current_user": current_user,
        "current_company": current_company,
        "user_companies": user_companies,
        "financial_years": financial_years,
        "license_status": license_status,
        "users": users,
        "max_users": max_users,
        "user_count": len(users),
        "license": license_doc,
        "breadcrumbs": [{"label": "Dashboard", "url": "/dashboard"}, {"label": "User Management"}],
    }
    return templates.TemplateResponse("users/list.html", context)


@router.post("/api/add")
async def add_user(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(...),
    admin_user: dict = Depends(get_admin_user),
):
    """Add a new user."""
    users_collection = await get_collection("users")

    # Check user limit
    user_count = await users_collection.count_documents({})
    max_users = await get_max_users()
    if user_count >= max_users:
        raise HTTPException(status_code=400, detail=f"User limit reached ({max_users}). Upgrade your plan for more users.")

    # Check duplicate username
    existing = await users_collection.find_one({"username": username})
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")

    # Get admin's companies so new user gets same access
    admin_companies = admin_user.get("companies", [])

    user_data = {
        "username": username,
        "email": email,
        "password_hash": get_password_hash(password),
        "full_name": full_name,
        "is_active": True,
        "companies": admin_companies,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    result = await users_collection.insert_one(user_data)
    return JSONResponse(content={"success": True, "id": str(result.inserted_id)})


@router.post("/api/{user_id}/toggle-active")
async def toggle_user_active(
    user_id: str,
    admin_user: dict = Depends(get_admin_user),
):
    """Toggle user active/inactive — admin only. Cannot deactivate yourself."""
    if str(admin_user["_id"]) == user_id:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account")

    users_collection = await get_collection("users")
    user = await users_collection.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    new_status = not user.get("is_active", True)
    await users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"is_active": new_status, "updated_at": datetime.utcnow()}}
    )
    return JSONResponse(content={"success": True, "is_active": new_status})


@router.post("/api/{user_id}/reset-password")
async def reset_user_password(
    user_id: str,
    new_password: str = Form(...),
    admin_user: dict = Depends(get_admin_user),
):
    """Reset a user's password — admin only."""
    users_collection = await get_collection("users")
    user = await users_collection.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"password_hash": get_password_hash(new_password), "updated_at": datetime.utcnow()}}
    )
    return JSONResponse(content={"success": True})


@router.post("/api/{user_id}/delete")
async def delete_user(
    user_id: str,
    admin_user: dict = Depends(get_admin_user),
):
    """Delete a user — admin only. Cannot delete yourself."""
    if str(admin_user["_id"]) == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    users_collection = await get_collection("users")
    result = await users_collection.delete_one({"_id": ObjectId(user_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")

    return JSONResponse(content={"success": True})
