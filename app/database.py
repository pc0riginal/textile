from motor.motor_asyncio import AsyncIOMotorClient
from config import settings

class Database:
    client: AsyncIOMotorClient = None
    database = None

db = Database()

async def get_database():
    return db.database

async def connect_to_mongo():
    db.client = AsyncIOMotorClient(settings.MONGODB_URL)
    db.database = db.client[settings.DATABASE_NAME]
    print(f"Connected to MongoDB: {settings.DATABASE_NAME}")

async def close_mongo_connection():
    if db.client:
        db.client.close()
        print("Disconnected from MongoDB")

# Collection helpers
async def get_collection(collection_name: str):
    database = await get_database()
    return database[collection_name]