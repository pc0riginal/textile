from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, JSONResponse
from datetime import datetime
from bson import ObjectId

from app import TEMPLATES_DIR
from app.dependencies import get_current_user, get_current_company, get_company_filter, get_template_context
from app.database import get_collection

router = APIRouter(prefix="/qualities")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

@router.get("")
async def list_qualities(
    context: dict = Depends(get_template_context)
):
    qualities_collection = await get_collection("qualities")
    qualities = await qualities_collection.find(
        get_company_filter(context["current_company"])
    ).sort("name", 1).to_list(None)
    
    context.update({
        "qualities": qualities,
        "breadcrumbs": [
            {"name": "Dashboard", "url": "/dashboard"},
            {"name": "Qualities", "url": "/qualities"}
        ]
    })
    return templates.TemplateResponse("qualities/list.html", context)

@router.get("/create")
async def create_quality_form(
    request: Request,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company)
):
    return templates.TemplateResponse("qualities/create.html", {
        "request": request,
        "current_user": current_user,
        "current_company": current_company,
        "breadcrumbs": [
            {"name": "Dashboard", "url": "/dashboard"},
            {"name": "Qualities", "url": "/qualities"},
            {"name": "Create", "url": "/qualities/create"}
        ]
    })

@router.post("/create")
async def create_quality(
    request: Request,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company),
    name: str = Form(...),
    display_name: str = Form(None),
    quality_main_group: str = Form(None),
    yarn_used: str = Form(None)
):
    qualities_collection = await get_collection("qualities")
    
    # Check for duplicate
    existing = await qualities_collection.find_one({
        **get_company_filter(current_company),
        "name": name
    })
    
    if existing:
        return templates.TemplateResponse("qualities/create.html", {
            "request": request,
            "current_user": current_user,
            "current_company": current_company,
            "error": "Quality with this name already exists",
            "breadcrumbs": [
                {"name": "Dashboard", "url": "/dashboard"},
                {"name": "Qualities", "url": "/qualities"},
                {"name": "Create", "url": "/qualities/create"}
            ]
        })
    
    quality_data = {
        **get_company_filter(current_company),
        "name": name,
        "display_name": display_name or name,
        "quality_main_group": quality_main_group,
        "yarn_used": yarn_used,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    await qualities_collection.insert_one(quality_data)
    return RedirectResponse(url="/qualities", status_code=302)

@router.get("/{quality_id}/edit")
async def edit_quality_form(
    request: Request,
    quality_id: str,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company)
):
    qualities_collection = await get_collection("qualities")
    quality = await qualities_collection.find_one({
        "_id": ObjectId(quality_id),
        **get_company_filter(current_company)
    })
    
    if not quality:
        raise HTTPException(status_code=404, detail="Quality not found")
    
    return templates.TemplateResponse("qualities/edit.html", {
        "request": request,
        "current_user": current_user,
        "current_company": current_company,
        "quality": quality,
        "breadcrumbs": [
            {"name": "Dashboard", "url": "/dashboard"},
            {"name": "Qualities", "url": "/qualities"},
            {"name": "Edit", "url": f"/qualities/{quality_id}/edit"}
        ]
    })

@router.post("/{quality_id}/edit")
async def update_quality(
    quality_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company),
    name: str = Form(...),
    display_name: str = Form(None),
    quality_main_group: str = Form(None),
    yarn_used: str = Form(None)
):
    qualities_collection = await get_collection("qualities")
    
    # Check for duplicate (excluding current quality)
    existing = await qualities_collection.find_one({
        **get_company_filter(current_company),
        "name": name,
        "_id": {"$ne": ObjectId(quality_id)}
    })
    
    if existing:
        quality = await qualities_collection.find_one({"_id": ObjectId(quality_id)})
        return templates.TemplateResponse("qualities/edit.html", {
            "request": request,
            "current_user": current_user,
            "current_company": current_company,
            "quality": quality,
            "error": "Quality with this name already exists",
            "breadcrumbs": [
                {"name": "Dashboard", "url": "/dashboard"},
                {"name": "Qualities", "url": "/qualities"},
                {"name": "Edit", "url": f"/qualities/{quality_id}/edit"}
            ]
        })
    
    update_data = {
        "name": name,
        "display_name": display_name or name,
        "quality_main_group": quality_main_group,
        "yarn_used": yarn_used,
        "updated_at": datetime.utcnow()
    }
    
    await qualities_collection.update_one(
        {"_id": ObjectId(quality_id), **get_company_filter(current_company)},
        {"$set": update_data}
    )
    
    return RedirectResponse(url="/qualities", status_code=302)

@router.delete("/{quality_id}")
async def delete_quality(
    quality_id: str,
    current_user: dict = Depends(get_current_user),
    current_company: dict = Depends(get_current_company)
):
    qualities_collection = await get_collection("qualities")
    result = await qualities_collection.delete_one({
        "_id": ObjectId(quality_id),
        **get_company_filter(current_company)
    })
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Quality not found")
    
    return JSONResponse(content={"message": "Quality deleted successfully"})

@router.get("/api/list")
async def get_qualities_api(
    current_company: dict = Depends(get_current_company)
):
    qualities_collection = await get_collection("qualities")
    qualities = await qualities_collection.find(
        get_company_filter(current_company)
    ).sort("name", 1).to_list(None)
    
    for q in qualities:
        q["_id"] = str(q["_id"])
        if "company_id" in q:
            q["company_id"] = str(q["company_id"])
        if "created_at" in q:
            del q["created_at"]
        if "updated_at" in q:
            del q["updated_at"]
    
    return JSONResponse(content=qualities)

@router.post("/api/quick-add")
async def quick_add_quality(
    request: Request,
    current_company: dict = Depends(get_current_company)
):
    data = await request.json()
    qualities_collection = await get_collection("qualities")
    
    existing = await qualities_collection.find_one({
        **get_company_filter(current_company),
        "name": data["name"]
    })
    
    if existing:
        return JSONResponse(content={"id": str(existing["_id"]), "name": existing["name"]})
    
    quality_data = {
        **get_company_filter(current_company),
        "name": data["name"],
        "display_name": data.get("display_name") or data["name"],
        "quality_main_group": data.get("quality_main_group"),
        "yarn_used": data.get("yarn_used"),
        "created_at": datetime.utcnow()
    }
    
    result = await qualities_collection.insert_one(quality_data)
    return JSONResponse(content={"id": str(result.inserted_id), "name": data["name"]})
