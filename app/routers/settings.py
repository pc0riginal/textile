from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from bson import ObjectId

from app.dependencies import get_current_user
from app.database import get_collection

router = APIRouter()

@router.get("/switch-company/{company_id}")
async def switch_company(
    company_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    companies_collection = await get_collection("companies")
    company = await companies_collection.find_one({"_id": ObjectId(company_id)})
    
    if not company:
        return RedirectResponse(url="/dashboard", status_code=302)
    
    referer = request.headers.get("referer", "/dashboard")
    response = RedirectResponse(url=referer, status_code=302)
    response.set_cookie("current_company_id", company_id)
    return response

@router.post("/switch-financial-year")
async def switch_financial_year(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    form_data = await request.form()
    financial_year = form_data.get("financial_year")
    company_id = request.cookies.get("current_company_id")
    
    if not company_id:
        return RedirectResponse(url="/dashboard", status_code=302)
    
    companies_collection = await get_collection("companies")
    company = await companies_collection.find_one({"_id": ObjectId(company_id)})
    
    if not company or financial_year not in company.get("financial_years", []):
        return RedirectResponse(url="/dashboard", status_code=302)
    
    await companies_collection.update_one(
        {"_id": ObjectId(company_id)},
        {"$set": {"financial_year": financial_year}}
    )
    
    referer = request.headers.get("referer", "/dashboard")
    return RedirectResponse(url=referer, status_code=302)

@router.post("/add-financial-year")
async def add_financial_year(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    form_data = await request.form()
    new_fy = form_data.get("new_financial_year")
    company_id = request.cookies.get("current_company_id")
    
    if not company_id or not new_fy:
        return RedirectResponse(url="/dashboard", status_code=302)
    
    companies_collection = await get_collection("companies")
    await companies_collection.update_one(
        {"_id": ObjectId(company_id)},
        {
            "$addToSet": {"financial_years": new_fy},
            "$set": {"financial_year": new_fy}
        }
    )
    
    referer = request.headers.get("referer", "/dashboard")
    return RedirectResponse(url=referer, status_code=302)
