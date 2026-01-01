from fastapi import APIRouter, Depends
from app.dependencies import get_current_user
from app.database import get_collection
from bson import ObjectId

router = APIRouter()

@router.get("/debug/user-info")
async def debug_user_info(current_user: dict = Depends(get_current_user)):
    companies_collection = await get_collection("companies")
    all_companies = await companies_collection.find({}).to_list(None)
    
    return {
        "user_id": str(current_user["_id"]),
        "username": current_user["username"],
        "user_companies_field": [str(c) if isinstance(c, ObjectId) else c for c in current_user.get("companies", [])],
        "all_companies_in_db": [{"id": str(c["_id"]), "name": c.get("name")} for c in all_companies]
    }
