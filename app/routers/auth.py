import os
from fastapi import APIRouter, Request, Form, HTTPException, status, Response
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from datetime import datetime, timedelta
from bson import ObjectId

from app import TEMPLATES_DIR
from app.database import get_collection
from app.auth import verify_password, get_password_hash, create_access_token, verify_token
from app.models.user import UserCreate, UserLogin
from app.services.audit_service import AuditService
from config import settings

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)

@router.get("/login")
async def login_page(request: Request):
    token = request.cookies.get("access_token")
    if token:
        try:
            verify_token(token)
            return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
        except Exception:
            pass
    return templates.TemplateResponse("auth/login.html", {"request": request})

@router.post("/login")
async def login(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...)
):
    users_collection = await get_collection("users")
    user = await users_collection.find_one({"username": username})
    
    if not user or not verify_password(password, user["password_hash"]):
        return templates.TemplateResponse(
            "auth/login.html", 
            {"request": request, "error": "Invalid username or password"}
        )
    
    if not user.get("is_active", True):
        return templates.TemplateResponse(
            "auth/login.html", 
            {"request": request, "error": "Account is deactivated"}
        )
    
    # Log login activity
    await AuditService.log_activity(
        company_id=str(user["companies"][0]) if user.get("companies") else "system",
        user_id=str(user["_id"]),
        username=user["username"],
        action="login",
        entity_type="user",
        ip_address=AuditService.get_client_ip(request)
    )
    
    # Create access token
    access_token = create_access_token(data={"sub": user["username"]})
    
    # Set cookie and redirect
    is_production = os.getenv("ENV", "development") == "production"
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
        secure=is_production
    )
    
    # Set current company if user has companies
    if user.get("companies"):
        response.set_cookie(
            key="current_company_id",
            value=str(user["companies"][0]),
            httponly=True,
            max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            samesite="lax",
            secure=is_production
        )
    
    return response

@router.get("/register")
async def register_page(request: Request):
    """Account setup — only allowed if no user exists yet (first-time setup)."""
    users_collection = await get_collection("users")
    user_count = await users_collection.count_documents({})
    if user_count > 0:
        return RedirectResponse(url="/auth/login", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse("auth/register.html", {"request": request})

@router.post("/register")
async def register(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(...),
):
    users_collection = await get_collection("users")

    # Block if a user already exists — single-tenant, one user per instance
    user_count = await users_collection.count_documents({})
    if user_count > 0:
        return RedirectResponse(url="/auth/login", status_code=status.HTTP_302_FOUND)

    # Create the sole user for this instance
    user_data = {
        "username": username,
        "email": email,
        "password_hash": get_password_hash(password),
        "full_name": full_name,
        "is_active": True,
        "companies": [],
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    result = await users_collection.insert_one(user_data)
    
    if result.inserted_id:
        return templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "success": "Account created successfully. Please login."}
        )
    else:
        return templates.TemplateResponse(
            "auth/register.html",
            {"request": request, "error": "Failed to create account"}
        )

@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/auth/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie("access_token")
    response.delete_cookie("current_company_id")
    return response