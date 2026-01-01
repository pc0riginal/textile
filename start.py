"""
Startup script for Textile ERP System
This script initializes the database and starts the application
"""
import asyncio
import subprocess
import sys
import os

async def main():
    print("=" * 60)
    print("🧵 TEXTILE ERP SYSTEM STARTUP")
    print("=" * 60)
    
    # Check if MongoDB is running (basic check)
    try:
        from app.database import connect_to_mongo, get_collection
        await connect_to_mongo()
        print("✅ MongoDB connection successful")
        
        # Check if demo data exists
        users_collection = await get_collection("users")
        admin_user = await users_collection.find_one({"username": "admin"})
        
        if not admin_user:
            print("🔧 Initializing database with demo data...")
            from init_db import init_database
            await init_database()
        else:
            print("✅ Demo data already exists")
            
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print("\n📋 Please ensure MongoDB is running:")
        print("   - Local: Start MongoDB service")
        print("   - Docker: Run 'docker-compose up -d mongodb'")
        return
    
    print("\n" + "=" * 60)
    print("🚀 STARTING TEXTILE ERP APPLICATION")
    print("=" * 60)
    print("📱 Application will be available at: http://localhost:8000")
    print("👤 Demo Login Credentials:")
    print("   Username: admin")
    print("   Password: admin123")
    print("\n🎯 Key Features Available:")
    print("   ✅ Multi-Company Management")
    print("   ✅ Party Management (Customers, Suppliers, Brokers, Transporters)")
    print("   ✅ Purchase Challans with Inventory Tracking")
    print("   ✅ Advanced Inventory Transfers (Multi-recipient)")
    print("   ✅ Material Lineage & Traceability")
    print("   ✅ Sales Invoices")
    print("   ✅ Payment Management")
    print("   ✅ Comprehensive Reports (PDF/Excel Export)")
    print("   ✅ Audit Logging")
    print("   ✅ Real-time Dashboard")
    print("=" * 60)
    print("\n🔄 Starting server...")
    
    # Start the FastAPI application
    try:
        subprocess.run([
            sys.executable, "-m", "uvicorn", 
            "main:app", 
            "--host", "0.0.0.0", 
            "--port", "8000", 
            "--reload"
        ])
    except KeyboardInterrupt:
        print("\n👋 Shutting down Textile ERP System...")
    except Exception as e:
        print(f"❌ Failed to start application: {e}")

if __name__ == "__main__":
    asyncio.run(main())