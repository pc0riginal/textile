import asyncio
from app.database import get_collection, connect_to_mongo

async def restore_financial_year():
    await connect_to_mongo()
    companies_collection = await get_collection("companies")
    
    companies = await companies_collection.find({}).to_list(None)
    
    for company in companies:
        financial_years = company.get("financial_years", [])
        if financial_years:
            # Set the first year as current
            await companies_collection.update_one(
                {"_id": company["_id"]},
                {"$set": {"financial_year": financial_years[0]}}
            )
            print(f"Set financial_year to {financial_years[0]} for company: {company['name']}")

asyncio.run(restore_financial_year())
