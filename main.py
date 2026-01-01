from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.database import connect_to_mongo, close_mongo_connection
from app.routers import auth, dashboard, companies, parties, purchase_invoices, transfers, invoices, payments, user, settings, banking, reports, qualities, debug

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await connect_to_mongo()
    yield
    # Shutdown
    await close_mongo_connection()

app = FastAPI(
    title="Textile ERP System",
    description="Complete Textile Business Management System",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Templates
templates = Jinja2Templates(directory="app/templates")

# Include routers
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(dashboard.router, prefix="", tags=["Dashboard"])
app.include_router(companies.router, prefix="/companies", tags=["Companies"])
app.include_router(parties.router, prefix="/parties", tags=["Parties"])
app.include_router(purchase_invoices.router, tags=["Purchase Invoices"])
app.include_router(transfers.router, prefix="/transfers", tags=["Inventory Transfers"])
app.include_router(invoices.router, prefix="/invoices", tags=["Sales Invoices"])
app.include_router(payments.router, prefix="/payments", tags=["Payments"])
app.include_router(user.router, prefix="", tags=["User"])
app.include_router(settings.router, prefix="", tags=["Settings"])
app.include_router(banking.router, prefix="/banking", tags=["Banking"])
app.include_router(reports.router, prefix="", tags=["Reports"])
app.include_router(qualities.router, tags=["Qualities"])
app.include_router(debug.router, prefix="", tags=["Debug"])

@app.get("/")
async def root(request: Request):
    token = request.cookies.get("access_token")
    if token:
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse("auth/login.html", {"request": request})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)