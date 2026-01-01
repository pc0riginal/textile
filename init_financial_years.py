import asyncio
from app.database import get_collection, connect_to_mongo

async def init_financial_years():
    await connect_to_mongo()
    companies_collection = await get_collection("companies")
    
    companies = await companies_collection.find({}).to_list(None)
    
    for company in companies:
        current_fy = company.get("financial_year", "")
        financial_years = company.get("financial_years", [])
        
        # If financial_years doesn't exist or is empty, initialize it
        if not financial_years:
            financial_years = [current_fy]
            await companies_collection.update_one(
                {"_id": company["_id"]},
                {"$set": {"financial_years": financial_years}}
            )
            print(f"Initialized financial_years for company: {company['name']} with [{current_fy}]")
        else:
            # Ensure current FY is in the list
            if current_fy not in financial_years:
                await companies_collection.update_one(
                    {"_id": company["_id"]},
                    {"$addToSet": {"financial_years": current_fy}}
                )
                print(f"Added {current_fy} to financial_years for company: {company['name']}")
            else:
                print(f"Company {company['name']} already has financial_years: {financial_years}")

asyncio.run(init_financial_years())
