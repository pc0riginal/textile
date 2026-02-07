from app.database import get_collection
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

async def init_database():
    users_collection = await get_collection("users")
    
    from datetime import datetime
    
    admin_user = {
        "username": "admin",
        "email": "admin@textile.com",
        "full_name": "Administrator",
        "password_hash": pwd_context.hash("admin123"),
        "role": "admin",
        "is_active": True,
        "companies": [],
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    await users_collection.insert_one(admin_user)
    print("✅ Admin user created (username: admin, password: admin123)")
