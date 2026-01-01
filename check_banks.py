import asyncio
from app.database import get_collection, connect_to_mongo

async def check():
    await connect_to_mongo()
    col = await get_collection('bank_accounts')
    banks = await col.find({}).to_list(None)
    print(f'Total banks in DB: {len(banks)}')
    for b in banks:
        print(f"Bank: {b.get('bank_name')} - Company ID: {b.get('company_id')}")

asyncio.run(check())
