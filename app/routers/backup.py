"""Backup management router — UI page + API endpoints."""
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse, RedirectResponse

from app import TEMPLATES_DIR
from app.dependencies import get_current_user
from app.services.backup_service import (
    get_backup_settings, save_backup_settings,
    create_backup, list_backups, restore_backup,
    sync_backups_to_new_mode, check_scheduled_backup,
)
from app.services.license_service import get_license
from config import settings as app_settings

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)


@router.get("")
async def backup_page(request: Request, current_user: dict = Depends(get_current_user)):
    """Backup management page."""
    license_doc = await get_license()
    backup_enabled = license_doc.get("backup_enabled", False) if license_doc else False
    backup_settings = await get_backup_settings() if backup_enabled else None

    # Clean mongo fields for JSON
    if backup_settings:
        backup_settings.pop("_id", None)
        if backup_settings.get("updated_at"):
            backup_settings["updated_at"] = backup_settings["updated_at"].isoformat()
        # Don't leak full google creds to frontend — just indicate connected or not
        if backup_settings.get("google_credentials"):
            backup_settings["google_connected"] = True
            del backup_settings["google_credentials"]
        else:
            backup_settings["google_connected"] = False

    # Check for Google auth result from redirect
    google_auth_success = request.query_params.get("google_auth") == "success"
    google_auth_error = request.query_params.get("google_auth_error", "")

    # Check scheduled backup on page load
    scheduled_msg = None
    if backup_enabled and backup_settings:
        result = await check_scheduled_backup()
        if result and not result.get("error"):
            scheduled_msg = f"Auto-backup created: {result.get('filename', '')}"
        elif result and result.get("error"):
            scheduled_msg = f"Scheduled backup failed: {result['error']}"

    return templates.TemplateResponse("backup/index.html", {
        "request": request,
        "current_user": current_user,
        "backup_enabled": backup_enabled,
        "backup_settings": backup_settings,
        "scheduled_msg": scheduled_msg or "",
        "google_auth_success": google_auth_success,
        "google_auth_error": google_auth_error,
    })


@router.get("/api/list")
async def api_list_backups(current_user: dict = Depends(get_current_user)):
    """List all backups."""
    backups = await list_backups()
    return JSONResponse(content={"success": True, "backups": backups})


@router.post("/api/create")
async def api_create_backup(current_user: dict = Depends(get_current_user)):
    """Manually trigger a backup."""
    try:
        result = await create_backup(created_by=current_user.get("username", "user"))
        return JSONResponse(content={"success": True, **result})
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/restore")
async def api_restore_backup(request: Request, current_user: dict = Depends(get_current_user)):
    """Restore from a backup."""
    body = await request.json()
    filename = body.get("filename", "")
    if not filename:
        raise HTTPException(status_code=400, detail="Filename required")
    try:
        result = await restore_backup(filename, restored_by=current_user.get("username", "user"))
        return JSONResponse(content={"success": True, **result})
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/settings")
async def api_save_settings(request: Request, current_user: dict = Depends(get_current_user)):
    """Save backup settings (mode, path, google folder id)."""
    body = await request.json()
    mode = body.get("mode", "offline")
    offline_path = body.get("offline_path", "")
    sync_old = body.get("sync_old", False)
    google_folder_id = body.get("google_folder_id", "")

    # For online mode, preserve existing google credentials from DB
    google_credentials = None
    if mode == "online":
        existing = await get_backup_settings()
        if existing and existing.get("google_credentials"):
            google_credentials = existing["google_credentials"]

    settings = await save_backup_settings(
        mode=mode,
        offline_path=offline_path,
        google_credentials=google_credentials,
        google_folder_id=google_folder_id,
        updated_by=current_user.get("username", "user"),
    )

    sync_result = None
    if sync_old:
        sync_result = await sync_backups_to_new_mode(mode, settings)

    settings.pop("_id", None)
    if settings.get("updated_at"):
        settings["updated_at"] = settings["updated_at"].isoformat()
    # Don't leak creds
    if settings.get("google_credentials"):
        settings["google_connected"] = True
        del settings["google_credentials"]
    else:
        settings["google_connected"] = False

    return JSONResponse(content={
        "success": True,
        "settings": settings,
        "sync_result": sync_result,
    })


@router.post("/api/google-save-creds")
async def api_google_save_creds(request: Request, current_user: dict = Depends(get_current_user)):
    """Save Google OAuth client ID/secret to DB (entered by user in UI)."""
    try:
        body = await request.json()
        client_id = body.get("client_id", "").strip()
        client_secret = body.get("client_secret", "").strip()

        if not client_id or not client_secret:
            raise HTTPException(status_code=400, detail="Client ID and Client Secret are required")

        # Save to backup settings — preserve existing fields
        existing = await get_backup_settings()
        google_credentials = (existing.get("google_credentials") or {}) if existing else {}
        google_credentials["client_id"] = client_id
        google_credentials["client_secret"] = client_secret

        await save_backup_settings(
            mode=existing.get("mode", "online") if existing else "online",
            offline_path=existing.get("offline_path", "") if existing else "",
            google_credentials=google_credentials,
            google_folder_id=existing.get("google_folder_id", "") if existing else "",
        )

        return JSONResponse(content={"success": True})
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to save credentials: {str(e)}")


@router.get("/api/google-auth-start")
async def google_auth_start(request: Request):
    """Redirect user to Google OAuth consent screen.

    Reads client_id/client_secret from DB (saved via google-save-creds).
    Falls back to config.py values if DB has none.
    """
    # Try DB first
    settings = await get_backup_settings()
    creds_data = settings.get("google_credentials", {}) if settings else {}
    client_id = creds_data.get("client_id", "") or app_settings.GOOGLE_CLIENT_ID
    client_secret = creds_data.get("client_secret", "") or app_settings.GOOGLE_CLIENT_SECRET

    if not client_id or not client_secret:
        raise HTTPException(
            status_code=500,
            detail="Google OAuth not configured. Please enter Client ID and Client Secret in backup settings."
        )

    try:
        from google_auth_oauthlib.flow import Flow
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="Google auth libraries not installed."
        )

    # Build redirect URI from the current request
    redirect_uri = str(request.base_url).rstrip("/") + "/backup/api/google-auth-callback"

    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri],
            }
        },
        scopes=["https://www.googleapis.com/auth/drive.file"],
        redirect_uri=redirect_uri,
    )
    auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
    return RedirectResponse(url=auth_url)


@router.get("/api/google-auth-callback")
async def google_auth_callback(request: Request):
    """Google redirects back here with ?code=... after user authorizes."""
    code = request.query_params.get("code", "")
    error = request.query_params.get("error", "")

    if error:
        return RedirectResponse(url=f"/backup?google_auth_error={error}")

    if not code:
        return RedirectResponse(url="/backup?google_auth_error=no_code")

    # Read client creds from DB first, fallback to config
    settings = await get_backup_settings()
    creds_data = (settings.get("google_credentials") or {}) if settings else {}
    client_id = creds_data.get("client_id", "") or app_settings.GOOGLE_CLIENT_ID
    client_secret = creds_data.get("client_secret", "") or app_settings.GOOGLE_CLIENT_SECRET

    try:
        from google_auth_oauthlib.flow import Flow
    except ImportError:
        return RedirectResponse(url="/backup?google_auth_error=libraries_missing")

    redirect_uri = str(request.base_url).rstrip("/") + "/backup/api/google-auth-callback"

    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri],
            }
        },
        scopes=["https://www.googleapis.com/auth/drive.file"],
        redirect_uri=redirect_uri,
    )

    try:
        flow.fetch_token(code=code)
    except Exception as e:
        return RedirectResponse(url=f"/backup?google_auth_error={str(e)[:100]}")

    creds = flow.credentials
    google_credentials = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes) if creds.scopes else [],
        "expiry": creds.expiry.isoformat() if creds.expiry else None,
    }

    import logging
    logging.getLogger("backup").warning(f"OAuth callback: saving tokens, has_token={bool(creds.token)}, has_refresh={bool(creds.refresh_token)}")

    # Save credentials into existing settings or create new
    existing = await get_backup_settings()
    await save_backup_settings(
        mode=existing.get("mode", "online") if existing else "online",
        offline_path=existing.get("offline_path", "") if existing else "",
        google_credentials=google_credentials,
        google_folder_id=existing.get("google_folder_id", "") if existing else "",
    )

    return RedirectResponse(url="/backup?google_auth=success")
