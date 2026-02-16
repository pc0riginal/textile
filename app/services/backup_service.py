"""Backup service — offline (local folder) and online (Google Drive) backups.

Scheduled: Monday & Friday auto-backup.
Manual: User can trigger anytime.
Mode switching: When switching from offline→online or vice versa, old backups are synced.
"""
import os
import sys
import json
import shutil
import subprocess
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from app.database import get_collection
from app.logger import logger
from config import settings as app_settings

# ── Backup directory (default, next to executable) ────────────────────────────
DEFAULT_BACKUP_DIR = os.path.join(
    os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
    else os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "backups"
)

BACKUP_SETTINGS_ID = "backup_settings"


async def get_backup_settings() -> Optional[Dict[str, Any]]:
    """Get backup configuration from DB."""
    col = await get_collection("app_settings")
    return await col.find_one({"_id": BACKUP_SETTINGS_ID})


async def save_backup_settings(
    mode: str,
    offline_path: str = "",
    google_credentials: Optional[Dict] = None,
    google_folder_id: str = "",
    updated_by: str = "system",
) -> Dict[str, Any]:
    """Save or update backup settings. mode = 'offline' | 'online'."""
    col = await get_collection("app_settings")
    doc = {
        "_id": BACKUP_SETTINGS_ID,
        "mode": mode,
        "offline_path": offline_path,
        "google_credentials": google_credentials,
        "google_folder_id": google_folder_id,
        "updated_at": datetime.utcnow(),
        "updated_by": updated_by,
    }
    await col.replace_one({"_id": BACKUP_SETTINGS_ID}, doc, upsert=True)
    logger.info(f"Backup settings updated: mode={mode} by {updated_by}")
    return doc


def _get_backup_dir(settings: Optional[Dict] = None) -> str:
    """Resolve the backup directory based on settings."""
    if settings and settings.get("mode") == "offline" and settings.get("offline_path"):
        return settings["offline_path"]
    return DEFAULT_BACKUP_DIR


def _run_mongodump() -> str:
    """Run mongodump and return the path to the zip file."""
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    db_name = app_settings.DATABASE_NAME
    mongo_url = app_settings.MONGODB_URL

    # Always dump to default dir first, then copy if needed
    os.makedirs(DEFAULT_BACKUP_DIR, exist_ok=True)
    dump_dir = os.path.join(DEFAULT_BACKUP_DIR, f"dump_{timestamp}")
    zip_base = os.path.join(DEFAULT_BACKUP_DIR, f"backup_{db_name}_{timestamp}")

    cmd = ["mongodump", f"--uri={mongo_url}", f"--db={db_name}", f"--out={dump_dir}"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(f"mongodump failed: {result.stderr}")
    except FileNotFoundError:
        raise RuntimeError(
            "mongodump not found. Install MongoDB Database Tools to enable backups."
        )

    zip_file = shutil.make_archive(zip_base, "zip", dump_dir)
    shutil.rmtree(dump_dir, ignore_errors=True)
    return zip_file


async def create_backup(created_by: str = "system", is_scheduled: bool = False) -> Dict[str, Any]:
    """Create a backup and store it according to current settings."""
    # Check license
    from app.services.license_service import get_license
    license_doc = await get_license()
    if not license_doc:
        raise ValueError("No license found")
    if not license_doc.get("backup_enabled"):
        raise ValueError("Backup is not enabled on your plan. Upgrade to Offline Premium or Online.")

    settings = await get_backup_settings()
    if not settings:
        raise ValueError("Backup not configured. Please set up backup mode in Settings → Backup.")

    # Create the dump
    zip_file = _run_mongodump()
    file_size = os.path.getsize(zip_file)
    filename = os.path.basename(zip_file)

    result = {
        "filename": filename,
        "size_bytes": file_size,
        "created_at": datetime.utcnow(),
        "created_by": created_by,
        "is_scheduled": is_scheduled,
        "mode": settings.get("mode", "offline"),
        "local_path": zip_file,
        "google_file_id": None,
    }

    mode = settings.get("mode", "offline")

    if mode == "offline":
        # Copy to user-chosen folder
        dest_dir = settings.get("offline_path", DEFAULT_BACKUP_DIR)
        if dest_dir and dest_dir != DEFAULT_BACKUP_DIR:
            os.makedirs(dest_dir, exist_ok=True)
            dest_file = os.path.join(dest_dir, filename)
            shutil.copy2(zip_file, dest_file)
            result["local_path"] = dest_file
            # Keep a copy in default dir too
            logger.info(f"Offline backup copied to {dest_file}")

    elif mode == "online":
        # Upload to Google Drive
        try:
            google_file_id = await _upload_to_google_drive(zip_file, filename, settings)
            result["google_file_id"] = google_file_id
            logger.info(f"Online backup uploaded to Google Drive: {google_file_id}")
        except Exception as e:
            logger.error(f"Google Drive upload failed: {e}")
            result["upload_error"] = str(e)

    # Record in DB
    col = await get_collection("backups")
    record = {
        "filename": filename,
        "size_bytes": file_size,
        "created_at": result["created_at"],
        "created_by": created_by,
        "is_scheduled": is_scheduled,
        "mode": mode,
        "local_path": result["local_path"],
        "google_file_id": result.get("google_file_id"),
    }
    await col.insert_one(record)

    logger.info(f"Backup created: {filename} ({file_size} bytes) by {created_by}")
    return {
        "filename": filename,
        "size_bytes": file_size,
        "created_at": result["created_at"].isoformat(),
        "created_by": created_by,
        "mode": mode,
        "google_file_id": result.get("google_file_id"),
        "upload_error": result.get("upload_error"),
    }


# ── Google Drive integration ──────────────────────────────────────────────────

async def _upload_to_google_drive(
    file_path: str, filename: str, settings: Dict
) -> str:
    """Upload a file to Google Drive. Returns the file ID."""
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError:
        raise RuntimeError(
            "Google Drive libraries not installed. Run: pip install google-api-python-client google-auth"
        )

    creds_data = settings.get("google_credentials")
    if not creds_data:
        raise ValueError("Google Drive not connected. Please authenticate first.")

    creds = Credentials(
        token=creds_data.get("token"),
        refresh_token=creds_data.get("refresh_token"),
        token_uri=creds_data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=creds_data.get("client_id"),
        client_secret=creds_data.get("client_secret"),
        scopes=creds_data.get("scopes", ["https://www.googleapis.com/auth/drive.file"]),
    )

    service = build("drive", "v3", credentials=creds)

    # Ensure the backup folder exists on Google Drive
    folder_id = settings.get("google_folder_id")
    folder_name = "Textile ERP Backups"

    if folder_id:
        # Verify the folder still exists (may have been deleted)
        try:
            service.files().get(fileId=folder_id, fields="id,trashed").execute()
        except Exception:
            folder_id = None  # Folder gone — recreate below

    if not folder_id:
        # Search for existing folder by name first
        query = (
            f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder'"
            " and trashed=false"
        )
        results = service.files().list(q=query, fields="files(id)", pageSize=1).execute()
        existing = results.get("files", [])
        if existing:
            folder_id = existing[0]["id"]
        else:
            # Create the folder
            folder_meta = {
                "name": folder_name,
                "mimeType": "application/vnd.google-apps.folder",
            }
            folder = service.files().create(body=folder_meta, fields="id").execute()
            folder_id = folder["id"]

        # Persist folder_id so we don't search/create every time
        col = await get_collection("app_settings")
        await col.update_one(
            {"_id": BACKUP_SETTINGS_ID},
            {"$set": {"google_folder_id": folder_id}},
        )

    file_metadata = {"name": filename, "mimeType": "application/zip", "parents": [folder_id]}
    media = MediaFileUpload(file_path, mimetype="application/zip", resumable=True)
    file = service.files().create(body=file_metadata, media_body=media, fields="id").execute()

    # Update token if refreshed
    if creds.token != creds_data.get("token"):
        col = await get_collection("app_settings")
        await col.update_one(
            {"_id": BACKUP_SETTINGS_ID},
            {"$set": {
                "google_credentials.token": creds.token,
                "google_credentials.expiry": creds.expiry.isoformat() if creds.expiry else None,
            }}
        )

    return file.get("id")


async def _list_google_drive_backups(settings: Dict) -> List[Dict]:
    """List backup files from Google Drive."""
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        return []

    creds_data = settings.get("google_credentials")
    if not creds_data:
        return []

    creds = Credentials(
        token=creds_data.get("token"),
        refresh_token=creds_data.get("refresh_token"),
        token_uri=creds_data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=creds_data.get("client_id"),
        client_secret=creds_data.get("client_secret"),
        scopes=creds_data.get("scopes", ["https://www.googleapis.com/auth/drive.file"]),
    )

    service = build("drive", "v3", credentials=creds)

    # Verify folder still exists; clear stale ID if deleted
    folder_id = settings.get("google_folder_id")
    if folder_id:
        try:
            f_check = service.files().get(fileId=folder_id, fields="id,trashed").execute()
            if f_check.get("trashed"):
                folder_id = None
        except Exception:
            folder_id = None

        if not folder_id:
            col = await get_collection("app_settings")
            await col.update_one(
                {"_id": BACKUP_SETTINGS_ID},
                {"$unset": {"google_folder_id": ""}},
            )

    query = "name contains 'backup_' and mimeType='application/zip' and trashed=false"
    if folder_id:
        query += f" and '{folder_id}' in parents"

    results = service.files().list(
        q=query, fields="files(id, name, size, createdTime)",
        orderBy="createdTime desc", pageSize=50
    ).execute()

    return [
        {
            "filename": f["name"],
            "google_file_id": f["id"],
            "size_bytes": int(f.get("size", 0)),
            "created_at": f.get("createdTime", ""),
        }
        for f in results.get("files", [])
    ]


# ── List & Restore ────────────────────────────────────────────────────────────

async def list_backups() -> List[Dict[str, Any]]:
    """List all backups from local + Google Drive."""
    settings = await get_backup_settings()
    backups = []

    # Local backups (default dir)
    if os.path.exists(DEFAULT_BACKUP_DIR):
        for f in sorted(os.listdir(DEFAULT_BACKUP_DIR), reverse=True):
            if f.endswith(".zip") and f.startswith("backup_"):
                filepath = os.path.join(DEFAULT_BACKUP_DIR, f)
                stat = os.stat(filepath)
                backups.append({
                    "filename": f,
                    "size_bytes": stat.st_size,
                    "created_at": datetime.utcfromtimestamp(stat.st_mtime).isoformat(),
                    "location": "local",
                    "path": filepath,
                })

    # Offline custom dir backups
    if settings and settings.get("mode") == "offline" and settings.get("offline_path"):
        custom_dir = settings["offline_path"]
        if os.path.exists(custom_dir) and custom_dir != DEFAULT_BACKUP_DIR:
            for f in sorted(os.listdir(custom_dir), reverse=True):
                if f.endswith(".zip") and f.startswith("backup_"):
                    filepath = os.path.join(custom_dir, f)
                    # Skip if already listed from default dir
                    if not any(b["filename"] == f for b in backups):
                        stat = os.stat(filepath)
                        backups.append({
                            "filename": f,
                            "size_bytes": stat.st_size,
                            "created_at": datetime.utcfromtimestamp(stat.st_mtime).isoformat(),
                            "location": "offline",
                            "path": filepath,
                        })

    # Google Drive backups
    if settings and settings.get("google_credentials"):
        try:
            drive_backups = await _list_google_drive_backups(settings)
            for b in drive_backups:
                b["location"] = "google_drive"
                backups.append(b)
        except Exception as e:
            logger.warning(f"Could not list Google Drive backups: {e}")

    # Sort by created_at descending
    backups.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return backups


async def restore_backup(filename: str, restored_by: str = "system") -> Dict[str, Any]:
    """Restore a MongoDB backup from a local zip archive."""
    from app.services.license_service import get_license
    license_doc = await get_license()
    if not license_doc or not license_doc.get("backup_enabled"):
        raise ValueError("Backup/restore is not enabled on your plan.")

    # Find the file
    zip_path = None
    for search_dir in [DEFAULT_BACKUP_DIR]:
        candidate = os.path.join(search_dir, filename)
        if os.path.exists(candidate):
            zip_path = candidate
            break

    settings = await get_backup_settings()
    if not zip_path and settings and settings.get("offline_path"):
        candidate = os.path.join(settings["offline_path"], filename)
        if os.path.exists(candidate):
            zip_path = candidate

    if not zip_path:
        raise ValueError(f"Backup file not found: {filename}")

    # Security: prevent path traversal
    real_path = os.path.realpath(zip_path)
    allowed_dirs = [os.path.realpath(DEFAULT_BACKUP_DIR)]
    if settings and settings.get("offline_path"):
        allowed_dirs.append(os.path.realpath(settings["offline_path"]))
    if not any(real_path.startswith(d) for d in allowed_dirs):
        raise ValueError("Invalid backup file path")

    db_name = app_settings.DATABASE_NAME
    mongo_url = app_settings.MONGODB_URL
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    extract_dir = os.path.join(DEFAULT_BACKUP_DIR, f"restore_{timestamp}")

    try:
        shutil.unpack_archive(zip_path, extract_dir)

        dump_path = os.path.join(extract_dir, db_name)
        if not os.path.isdir(dump_path):
            for entry in os.listdir(extract_dir):
                candidate = os.path.join(extract_dir, entry, db_name)
                if os.path.isdir(candidate):
                    dump_path = candidate
                    break

        if not os.path.isdir(dump_path):
            raise ValueError("Could not find database dump inside the backup archive")

        cmd = [
            "mongorestore", f"--uri={mongo_url}", f"--db={db_name}",
            "--drop", dump_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(f"mongorestore failed: {result.stderr}")
    except FileNotFoundError:
        raise RuntimeError("mongorestore not found. Install MongoDB Database Tools.")
    finally:
        shutil.rmtree(extract_dir, ignore_errors=True)

    logger.info(f"Backup restored: {filename} by {restored_by}")
    return {"filename": filename, "restored_at": datetime.utcnow().isoformat(), "restored_by": restored_by}


# ── Scheduled backup check ────────────────────────────────────────────────────

SCHEDULE_DAYS = [0, 4]  # Monday=0, Friday=4


async def check_scheduled_backup() -> Optional[Dict[str, Any]]:
    """Check if a scheduled backup is due today. Called on app startup.

    Returns backup info if one was created, or None if not due / already done.
    """
    from app.services.license_service import get_license
    license_doc = await get_license()
    if not license_doc or not license_doc.get("backup_enabled"):
        return None

    settings = await get_backup_settings()
    if not settings:
        return None  # Not configured yet

    today = datetime.utcnow().date()
    weekday = today.weekday()

    if weekday not in SCHEDULE_DAYS:
        return None

    # Check if we already backed up today
    col = await get_collection("backups")
    today_start = datetime.combine(today, datetime.min.time())
    today_end = today_start + timedelta(days=1)
    existing = await col.find_one({
        "is_scheduled": True,
        "created_at": {"$gte": today_start, "$lt": today_end},
    })
    if existing:
        return None  # Already done today

    try:
        result = await create_backup(created_by="scheduled", is_scheduled=True)
        return result
    except Exception as e:
        logger.error(f"Scheduled backup failed: {e}")
        return {"error": str(e)}


async def sync_backups_to_new_mode(new_mode: str, settings: Dict) -> Dict[str, Any]:
    """When user switches backup mode, sync existing backups to the new destination.

    offline→online: Upload all local backups to Google Drive.
    online→offline: Download all Google Drive backups to local folder.
    """
    synced = 0
    errors = []

    if new_mode == "online":
        # Upload local backups to Google Drive
        for search_dir in [DEFAULT_BACKUP_DIR]:
            if not os.path.exists(search_dir):
                continue
            for f in os.listdir(search_dir):
                if f.endswith(".zip") and f.startswith("backup_"):
                    filepath = os.path.join(search_dir, f)
                    try:
                        await _upload_to_google_drive(filepath, f, settings)
                        synced += 1
                    except Exception as e:
                        errors.append(f"{f}: {str(e)}")

        # Also from custom offline dir
        if settings.get("offline_path") and settings["offline_path"] != DEFAULT_BACKUP_DIR:
            custom_dir = settings["offline_path"]
            if os.path.exists(custom_dir):
                for f in os.listdir(custom_dir):
                    if f.endswith(".zip") and f.startswith("backup_"):
                        filepath = os.path.join(custom_dir, f)
                        try:
                            await _upload_to_google_drive(filepath, f, settings)
                            synced += 1
                        except Exception as e:
                            errors.append(f"{f}: {str(e)}")

    elif new_mode == "offline":
        # Download Google Drive backups to local
        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            import io

            creds_data = settings.get("google_credentials", {})
            creds = Credentials(
                token=creds_data.get("token"),
                refresh_token=creds_data.get("refresh_token"),
                token_uri=creds_data.get("token_uri", "https://oauth2.googleapis.com/token"),
                client_id=creds_data.get("client_id"),
                client_secret=creds_data.get("client_secret"),
            )
            service = build("drive", "v3", credentials=creds)

            drive_backups = await _list_google_drive_backups(settings)
            dest_dir = settings.get("offline_path", DEFAULT_BACKUP_DIR)
            os.makedirs(dest_dir, exist_ok=True)

            for b in drive_backups:
                dest_file = os.path.join(dest_dir, b["filename"])
                if os.path.exists(dest_file):
                    continue  # Already exists locally
                try:
                    request = service.files().get_media(fileId=b["google_file_id"])
                    with open(dest_file, "wb") as fh:
                        downloader = request.execute()
                        if isinstance(downloader, bytes):
                            fh.write(downloader)
                        synced += 1
                except Exception as e:
                    errors.append(f"{b['filename']}: {str(e)}")
        except ImportError:
            errors.append("Google Drive libraries not installed")
        except Exception as e:
            errors.append(str(e))

    return {"synced": synced, "errors": errors}
