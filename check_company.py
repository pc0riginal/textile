import asyncio
from app.database import get_collection, connect_to_mongo
from bson import ObjectId

async def check():
    await connect_to_mongo()
    companies_collection = await get_collection("companies")
    
    company = await companies_collection.find_one({"_id": ObjectId("69259615f381607ca7e596be")})
    
    if company:
        print(f"Company: {company['name']}")
        print(f"Current financial_year: {company.get('financial_year')}")
        print(f"financial_years array: {company.get('financial_years', [])}")
    else:
        print("Company not found")

asyncio.run(check())
