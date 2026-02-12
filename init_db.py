from app.database import get_collection
from app.auth import get_password_hash


async def init_database():
    """Create default admin user if no users exist.
    
    Single-tenant: each instance has one user. This seeds a default
    account for initial access. The customer can change credentials
    from the profile/settings page after first login.
    """
    users_collection = await get_collection("users")

    # Skip if a user already exists
    existing = await users_collection.count_documents({})
    if existing > 0:
        print("ℹ️  User already exists — skipping seed.")
        return

    from datetime import datetime

    admin_user = {
        "username": "admin",
        "email": "admin@textile.com",
        "full_name": "Administrator",
        "password_hash": get_password_hash("admin123"),
        "is_active": True,
        "companies": [],
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }

    await users_collection.insert_one(admin_user)
    print("✅ Admin user created (username: admin, password: admin123)")
