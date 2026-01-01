from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from bson import ObjectId

from app.dependencies import get_current_user, get_current_company
from app.database import get_collection

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/profile")
async def profile(
    request: Request,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company)
):
    companies_collection = await get_collection("companies")
    user_companies = await companies_collection.find(
        {"_id": {"$in": [ObjectId(cid) for cid in current_user.get("companies", [])]}}
    ).to_list(None)
    
    return templates.TemplateResponse("user/profile.html", {
        "request": request,
        "current_user": current_user,
        "current_company": current_company,
        "user_companies": user_companies
    })

@router.get("/settings")
async def settings(
    request: Request,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company)
):
    companies_collection = await get_collection("companies")
    user_companies = await companies_collection.find(
        {"_id": {"$in": [ObjectId(cid) for cid in current_user.get("companies", [])]}}
    ).to_list(None)
    
    return templates.TemplateResponse("user/settings.html", {
        "request": request,
        "current_user": current_user,
        "current_company": current_company,
        "user_companies": user_companies
    })

@router.get("/banking")
async def banking(
    request: Request,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company)
):
    companies_collection = await get_collection("companies")
    user_companies = await companies_collection.find(
        {"_id": {"$in": [ObjectId(cid) for cid in current_user.get("companies", [])]}}
    ).to_list(None)
    
    return templates.TemplateResponse("banking/index.html", {
        "request": request,
        "current_user": current_user,
        "current_company": current_company,
        "user_companies": user_companies
    })

@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/auth/login", status_code=302)
    response.delete_cookie("access_token")
    return response
