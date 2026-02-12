from fastapi import APIRouter, Request, Depends, Form, HTTPException, Query
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, JSONResponse

from app import TEMPLATES_DIR
from app.dependencies import get_current_user
from app.services.license_service import (
    activate_license, check_license_status, get_license,
    renew_license, register_device, PLANS,
    extend_trial, suspend_license, reactivate_license,
    change_plan, reset_devices, get_admin_log,
    generate_license_key, create_backup, restore_backup, list_backups,
)
from app.enums import PlanType
from config import settings as app_settings

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)


def verify_admin_secret(request: Request):
    """Verify admin secret from query param or cookie."""
    secret = request.query_params.get("secret") or request.cookies.get("admin_secret")
    if not app_settings.ADMIN_SECRET:
        raise HTTPException(status_code=500, detail="ADMIN_SECRET not configured on this instance")
    if secret != app_settings.ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Invalid admin secret")


# ── Public endpoints ──────────────────────────────────────────────────────────

@router.get("/pricing")
async def pricing_page(request: Request):
    """Public pricing page — no auth required."""
    return templates.TemplateResponse("license/pricing.html", {
        "request": request,
        "plans": PLANS,
    })


@router.get("/activate")
async def activate_page(request: Request):
    """License activation page — shown on first setup or when license is missing."""
    license_status = await check_license_status()
    return templates.TemplateResponse("license/activate.html", {
        "request": request,
        "license_status": license_status,
    })


@router.get("/suspended")
async def suspended_page(request: Request):
    """Shown when the license has been suspended by admin."""
    license_doc = await get_license()
    # Get the last suspend action for the reason
    reason = "Your license has been suspended."
    if license_doc:
        actions = license_doc.get("admin_actions", [])
        for action in reversed(actions):
            if action.get("action") == "suspend":
                reason = action.get("reason", reason)
                break
    return templates.TemplateResponse("license/suspended.html", {
        "request": request,
        "reason": reason,
        "license": license_doc,
    })


@router.get("/expired")
async def expired_page(request: Request):
    """Shown when the license has expired."""
    license_doc = await get_license()
    return templates.TemplateResponse("license/expired.html", {
        "request": request,
        "license": license_doc,
    })


@router.post("/activate")
async def activate(request: Request, license_key: str = Form(...)):
    """Activate a license key."""
    try:
        result = await activate_license(license_key, activated_by="setup")
        return RedirectResponse(url="/", status_code=303)
    except ValueError as e:
        license_status = await check_license_status()
        return templates.TemplateResponse("license/activate.html", {
            "request": request,
            "license_status": license_status,
            "error": str(e),
        })


@router.post("/activate/trial")
async def activate_trial(request: Request):
    """One-click free trial activation — generates and activates a trial key."""
    # Check if license already exists
    existing = await get_license()
    if existing:
        return RedirectResponse(url="/", status_code=303)

    key = generate_license_key("free_trial", "Trial User")
    try:
        await activate_license(key, activated_by="self-service-trial")
        return RedirectResponse(url="/", status_code=303)
    except ValueError as e:
        license_status = await check_license_status()
        return templates.TemplateResponse("license/activate.html", {
            "request": request,
            "license_status": license_status,
            "error": str(e),
        })


# ── Authenticated user endpoints ──────────────────────────────────────────────

@router.get("/status")
async def license_status_page(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """License status page for logged-in users."""
    status = await check_license_status()
    license_doc = await get_license()
    return templates.TemplateResponse("license/status.html", {
        "request": request,
        "current_user": current_user,
        "status": status,
        "license": license_doc,
    })


@router.get("/api/status")
async def license_status_api():
    """API endpoint for license status check."""
    status = await check_license_status()
    # Serialize datetimes for JSON
    for key, val in status.items():
        if hasattr(val, "isoformat"):
            status[key] = val.isoformat()
    return JSONResponse(content=status)


@router.post("/renew")
async def renew(current_user: dict = Depends(get_current_user)):
    """Renew online plan license."""
    try:
        result = await renew_license(renewed_by=str(current_user["_id"]))
        return JSONResponse(content={
            "success": True,
            "new_expiry": result["new_expiry"].isoformat(),
            "days_remaining": result["days_remaining"],
        })
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Admin endpoints (protected by ADMIN_SECRET) ──────────────────────────────

@router.get("/admin")
async def license_admin_page(request: Request):
    """Admin license management page. Access: /license/admin?secret=YOUR_ADMIN_SECRET"""
    verify_admin_secret(request)
    status = await check_license_status()
    license_doc = await get_license()
    admin_log = await get_admin_log()
    response = templates.TemplateResponse("license/admin.html", {
        "request": request,
        "status": status,
        "license": license_doc,
        "admin_log": admin_log,
        "plan_types": list(PlanType),
        "plans": PLANS,
    })
    # Set cookie so subsequent admin AJAX calls don't need ?secret in URL
    secret = request.query_params.get("secret")
    if secret:
        response.set_cookie("admin_secret", secret, httponly=True, max_age=3600, samesite="lax")
    return response


@router.post("/admin/extend")
async def admin_extend_trial(request: Request, extra_days: int = Form(...)):
    """Extend trial/expiry by N days."""
    verify_admin_secret(request)
    try:
        result = await extend_trial(extra_days, extended_by="admin")
        return JSONResponse(content={
            "success": True,
            "new_expiry": result["new_expiry"].isoformat(),
            "days_remaining": result["days_remaining"],
        })
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/admin/suspend")
async def admin_suspend(request: Request, reason: str = Form("Admin action")):
    """Suspend the license immediately."""
    verify_admin_secret(request)
    try:
        result = await suspend_license(reason, suspended_by="admin")
        return JSONResponse(content={"success": True, **result})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/admin/reactivate")
async def admin_reactivate(request: Request):
    """Reactivate a suspended license."""
    verify_admin_secret(request)
    try:
        result = await reactivate_license(reactivated_by="admin")
        return JSONResponse(content={"success": True, **result})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/admin/change-plan")
async def admin_change_plan(request: Request, new_plan: str = Form(...)):
    """Change the license plan."""
    verify_admin_secret(request)
    try:
        result = await change_plan(new_plan, changed_by="admin")
        return JSONResponse(content={
            "success": True,
            "old_plan": result["old_plan"],
            "new_plan": result["new_plan"],
            "plan_name": result["plan_name"],
            "expires_at": result["expires_at"].isoformat() if result["expires_at"] else None,
        })
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/admin/reset-devices")
async def admin_reset_devices(request: Request):
    """Clear all registered devices."""
    verify_admin_secret(request)
    try:
        result = await reset_devices(reset_by="admin")
        return JSONResponse(content={"success": True, "cleared": result["cleared"]})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/admin/log")
async def admin_action_log(request: Request):
    """Get admin action history as JSON."""
    verify_admin_secret(request)
    log = await get_admin_log()
    for entry in log:
        for key, val in entry.items():
            if hasattr(val, "isoformat"):
                entry[key] = val.isoformat()
    return JSONResponse(content=log)


@router.post("/admin/generate-key")
async def admin_generate_key(
    request: Request,
    plan: str = Form(...),
    customer_name: str = Form(...),
    customer_email: str = Form(""),
    customer_phone: str = Form(""),
):
    """Generate a license key for a customer."""
    verify_admin_secret(request)
    if plan not in [p.value for p in PlanType]:
        raise HTTPException(status_code=400, detail=f"Unknown plan: {plan}")
    key = generate_license_key(plan, customer_name, customer_email, customer_phone)
    return JSONResponse(content={"success": True, "license_key": key})


# ── Backup & Restore endpoints ────────────────────────────────────────────────

@router.get("/backup/list")
async def backup_list(request: Request, current_user: dict = Depends(get_current_user)):
    """List available backups."""
    # Check if backup is enabled
    status = await check_license_status()
    if not status.get("backup_enabled"):
        raise HTTPException(status_code=403, detail="Backup is not enabled on your plan")
    backups = list_backups()
    return JSONResponse(content={"success": True, "backups": backups})


@router.post("/backup/create")
async def backup_create(request: Request, current_user: dict = Depends(get_current_user)):
    """Create a new backup."""
    try:
        result = await create_backup(created_by=str(current_user["_id"]))
        return JSONResponse(content={"success": True, **result})
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/backup/restore")
async def backup_restore(
    request: Request,
    filename: str = Form(...),
    current_user: dict = Depends(get_current_user),
):
    """Restore from a backup file."""
    try:
        result = await restore_backup(filename, restored_by=str(current_user["_id"]))
        return JSONResponse(content={"success": True, **result})
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))
