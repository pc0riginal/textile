from fastapi import Depends, HTTPException, status, Request
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from bson import ObjectId
from app.auth import verify_token
from app.database import get_collection

security = HTTPBearer(auto_error=False)

async def get_current_user(request: Request, credentials: HTTPAuthorizationCredentials = Depends(security)):
    # Try to get token from cookie first
    token = request.cookies.get("access_token")
    
    if not token and credentials:
        token = credentials.credentials
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            detail="Not authenticated",
            headers={"Location": "/auth/login"}
        )
    
    try:
        username = verify_token(token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            detail="Invalid token",
            headers={"Location": "/auth/login"}
        )
    
    users_collection = await get_collection("users")
    user = await users_collection.find_one({"username": username})
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            detail="User not found",
            headers={"Location": "/auth/login"}
        )
    
    return user


async def get_admin_user(current_user: dict = Depends(get_current_user)):
    """Dependency — alias for get_current_user (no admin role distinction).
    
    Kept for backward compatibility with routers that reference it.
    All users have equal privileges; license management is gated by ADMIN_SECRET.
    """
    return current_user

async def get_current_company(request: Request, current_user: dict = Depends(get_current_user)):
    company_id = request.cookies.get("current_company_id")
    companies_collection = await get_collection("companies")
    company = None
    
    # Try cookie first
    if company_id:
        try:
            company = await companies_collection.find_one({"_id": ObjectId(company_id)})
        except (Exception):
            pass
    
    # If cookie invalid, find valid company from user's list
    if not company and current_user.get("companies"):
        for cid in current_user["companies"]:
            try:
                cid_str = str(cid) if isinstance(cid, ObjectId) else cid
                company = await companies_collection.find_one({"_id": ObjectId(cid_str)})
                if company:
                    break
            except Exception:
                continue
    
    if not company:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            detail="No company found. Please create a company first.",
            headers={"Location": "/companies/new"}
        )
    
    return company

def get_company_filter(company: dict):
    """Get base filter for company and financial year"""
    return {
        "company_id": ObjectId(company["_id"]),
        "financial_year": company.get("financial_year", "")
    }

async def get_current_company_optional(request: Request, current_user: dict = Depends(get_current_user)):
    """Optional company dependency - returns None if no company exists"""
    try:
        return await get_current_company(request, current_user)
    except HTTPException:
        return None

async def get_template_context(request: Request, current_user: dict = Depends(get_current_user), current_company: dict = Depends(get_current_company)):
    """Get common template context including user companies and financial years"""
    from app.services.license_service import check_license_status

    companies_collection = await get_collection("companies")
    user_companies = await companies_collection.find({"_id": {"$in": [ObjectId(cid) for cid in current_user.get("companies", [])]}}).to_list(None)
    
    # Get all unique financial years from current company only
    financial_years = current_company.get("financial_years", [])
    if not financial_years and current_company.get("financial_year"):
        financial_years = [current_company.get("financial_year")]

    license_status = await check_license_status()

    return {
        "request": request,
        "current_user": current_user,
        "current_company": current_company,
        "user_companies": user_companies,
        "financial_years": financial_years,
        "license_status": license_status,
    }