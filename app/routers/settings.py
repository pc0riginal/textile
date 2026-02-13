from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse, JSONResponse
from bson import ObjectId

from app.dependencies import get_current_user, get_current_company
from app.database import get_collection

router = APIRouter()


@router.get("/api/navbar-data")
async def navbar_data(
    request: Request,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company),
):
    """Return company list and FY list for the navbar dropdowns."""
    companies_collection = await get_collection("companies")
    user_company_ids = [ObjectId(cid) for cid in current_user.get("companies", [])]
    user_companies = await companies_collection.find({"_id": {"$in": user_company_ids}}).to_list(None)

    financial_years = current_company.get("financial_years", [])
    if not financial_years and current_company.get("financial_year"):
        financial_years = [current_company["financial_year"]]

    return JSONResponse(content={
        "current_company": {
            "id": str(current_company["_id"]),
            "name": current_company.get("name", ""),
            "financial_year": current_company.get("financial_year", ""),
        },
        "companies": [
            {"id": str(c["_id"]), "name": c.get("name", "")}
            for c in user_companies
        ],
        "financial_years": financial_years,
    })


@router.get("/switch-company/{company_id}")
async def switch_company(
    company_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    # Verify the company exists and belongs to the user
    companies_collection = await get_collection("companies")
    company = await companies_collection.find_one({"_id": ObjectId(company_id)})

    if not company:
        return RedirectResponse(url="/dashboard", status_code=303)

    # Verify user has access to this company
    user_company_ids = [str(c) for c in current_user.get("companies", [])]
    if company_id not in user_company_ids:
        return RedirectResponse(url="/dashboard", status_code=303)

    redirect_url = request.headers.get("referer", "/dashboard")
    response = RedirectResponse(url=redirect_url, status_code=303)
    response.set_cookie("current_company_id", company_id, httponly=True, samesite="lax")
    return response


@router.post("/switch-financial-year")
async def switch_financial_year(
    request: Request,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company),
):
    form_data = await request.form()
    financial_year = form_data.get("financial_year")

    if not financial_year:
        return RedirectResponse(url="/dashboard", status_code=303)

    company_id = str(current_company["_id"])

    # Verify the FY exists for this company
    if financial_year not in current_company.get("financial_years", []):
        return RedirectResponse(url="/dashboard", status_code=303)

    # Update the company's active financial year
    companies_collection = await get_collection("companies")
    await companies_collection.update_one(
        {"_id": current_company["_id"]},
        {"$set": {"financial_year": financial_year}},
    )

    redirect_url = request.headers.get("referer", "/dashboard")
    response = RedirectResponse(url=redirect_url, status_code=303)
    response.set_cookie("current_company_id", company_id, httponly=True, samesite="lax")
    return response
