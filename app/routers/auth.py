from fastapi import APIRouter, Request, Form, HTTPException, status, Response
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from datetime import datetime, timedelta
from bson import ObjectId

from app.database import get_collection
from app.auth import verify_password, get_password_hash, create_access_token
from app.models.user import UserCreate, UserLogin
from app.services.audit_service import AuditService

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/login")
async def login_page(request: Request):
    token = request.cookies.get("access_token")
    if token:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
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
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=1800,  # 30 minutes
        samesite="lax"
    )
    
    # Set current company if user has companies
    if user.get("companies"):
        response.set_cookie(
            key="current_company_id",
            value=str(user["companies"][0]),
            httponly=True,
            max_age=1800
        )
    
    return response

@router.get("/register")
async def register_page(request: Request):
    return templates.TemplateResponse("auth/register.html", {"request": request})

@router.post("/register")
async def register(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(...),
    role: str = Form(default="accountant")
):
    users_collection = await get_collection("users")
    
    # Check if user exists
    existing_user = await users_collection.find_one({
        "$or": [{"username": username}, {"email": email}]
    })
    
    if existing_user:
        return templates.TemplateResponse(
            "auth/register.html",
            {"request": request, "error": "Username or email already exists"}
        )
    
    # Create user
    user_data = {
        "username": username,
        "email": email,
        "password_hash": get_password_hash(password),
        "full_name": full_name,
        "role": role,
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