from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app import BASE_DIR, TEMPLATES_DIR, STATIC_DIR
from app.database import connect_to_mongo, close_mongo_connection
from app.indexes import ensure_indexes
from app.routers import auth, dashboard, companies, parties, purchase_invoices, invoices, payments, user, settings, banking, reports, qualities
from app.routers import license as license_router
from app.routers import backup as backup_router
from app.routers import users as users_router
from app.services.license_service import check_license_status
from config import settings as app_settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await connect_to_mongo()
    await ensure_indexes()
    yield
    # Shutdown
    await close_mongo_connection()

app = FastAPI(
    title="Textile ERP System",
    description="Complete Textile Business Management System",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware — restrict origins in production
allowed_origins = app_settings.ALLOWED_ORIGINS.split(",") if hasattr(app_settings, "ALLOWED_ORIGINS") and app_settings.ALLOWED_ORIGINS else ["http://localhost:8000"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def license_check_middleware(request: Request, call_next):
    """Block access to the app if no valid license — allow license/auth/static routes."""
    path = request.url.path
    open_prefixes = ("/license", "/auth", "/static", "/docs", "/openapi.json", "/redoc")
    if any(path.startswith(p) for p in open_prefixes):
        return await call_next(request)

    status = await check_license_status()
    if not status["valid"]:
        reason = status.get("reason", "no_license")
        if reason == "suspended":
            return RedirectResponse(url="/license/suspended", status_code=302)
        elif reason == "expired":
            return RedirectResponse(url="/license/expired", status_code=302)
        elif reason == "device_limit":
            return RedirectResponse(url="/license/activate?error=device_limit", status_code=302)
        else:
            return RedirectResponse(url="/license/activate", status_code=302)

    return await call_next(request)

# Templates
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Include routers
app.include_router(license_router.router, prefix="/license", tags=["License"])
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(dashboard.router, prefix="", tags=["Dashboard"])
app.include_router(companies.router, prefix="/companies", tags=["Companies"])
app.include_router(parties.router, prefix="/parties", tags=["Parties"])
app.include_router(purchase_invoices.router, tags=["Purchase Invoices"])
app.include_router(invoices.router, prefix="/invoices", tags=["Sales Invoices"])
app.include_router(payments.router, prefix="/payments", tags=["Payments"])
app.include_router(user.router, prefix="", tags=["User"])
app.include_router(settings.router, prefix="", tags=["Settings"])
app.include_router(banking.router, prefix="/banking", tags=["Banking"])
app.include_router(reports.router, prefix="", tags=["Reports"])
app.include_router(qualities.router, tags=["Qualities"])
app.include_router(backup_router.router, prefix="/backup", tags=["Backup"])
app.include_router(users_router.router, prefix="/users", tags=["Users"])

# Debug router — only in development
import os
if os.getenv("DEBUG", "false").lower() == "true":
    from app.routers import debug
    app.include_router(debug.router, prefix="", tags=["Debug"])

@app.get("/")
async def root(request: Request):
    # Check license first
    status = await check_license_status()
    if not status["valid"]:
        return RedirectResponse(url="/license/activate", status_code=302)

    # Check if any user exists — if not, send to registration
    from app.database import get_collection
    users = await get_collection("users")
    if await users.count_documents({}) == 0:
        return RedirectResponse(url="/auth/register", status_code=302)

    # If logged in, go to dashboard
    token = request.cookies.get("access_token")
    if token:
        return RedirectResponse(url="/dashboard", status_code=302)

    return RedirectResponse(url="/auth/login", status_code=302)


@app.post("/api/shutdown")
async def shutdown_server(request: Request):
    """Gracefully shut down the application (for desktop/offline use)."""
    import signal
    from fastapi.responses import JSONResponse

    # Verify user is authenticated
    token = request.cookies.get("access_token")
    if not token:
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)

    # Schedule shutdown after response is sent
    import asyncio
    loop = asyncio.get_event_loop()
    loop.call_later(1, lambda: os.kill(os.getpid(), signal.SIGTERM))

    return JSONResponse({"message": "Server shutting down..."})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)