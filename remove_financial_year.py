import asyncio
from app.database import get_collection, connect_to_mongo

async def remove_financial_year():
    await connect_to_mongo()
    companies_collection = await get_collection("companies")
    
    result = await companies_collection.update_many(
        {},
        {"$unset": {"financial_year": ""}}
    )
    
    print(f"Removed financial_year field from {result.modified_count} companies")

asyncio.run(remove_financial_year())
