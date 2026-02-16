"""License management — validates plan, expiry, and device limits per instance."""
import hashlib
import json
import base64
import platform
import uuid
import subprocess
import os
import sys
import shutil
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from bson import ObjectId

from app.database import get_collection
from app.enums import PlanType, LicenseStatus
from app.logger import logger

# ── RSA keys for license signing ──────────────────────────────────────────────
# Only the PUBLIC key is embedded in the distributed app.
# The PRIVATE key stays on the developer's admin machine (in .env or separate file).
# Even with full source access, nobody can forge keys without the private key.

from config import settings as app_settings

# Public key — embedded in app, used to VERIFY license keys
_RSA_PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA3GZ6XNszSK/yL01zc5OZ
lVStpAG5kok7QLqIys7DEbgX8M3ZlbPQoLc93DUO/SLkKZR7HAZmzYYPFrnreDVj
ex9xgSsw1RmU+DCrBNfdrNHYNww2qKE+SKCZT2Q80HPDzUF85Q9T6GNH0w8+q76u
fviEiopmiZFWztoioYYoprL74nTMQglUmB+YOTr1yLSAGAg909bwFMOQ3geWrRxm
Rr/WyYExqj/4Jx0R2Jt/BZ/jkf2e2HHyVgGNB5492hykDhr17bWZxcu1FycA6vSo
kqIJrtD5Jgn9WOiCBS/KAutgX+3g4Ebm6zNm5TEqq5+3itjW2kpnKV4xtOfNITwf
lQIDAQAB
-----END PUBLIC KEY-----"""


def _get_public_key():
    """Load the RSA public key for signature verification."""
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    return load_pem_public_key(_RSA_PUBLIC_KEY_PEM.encode())


def _get_private_key():
    """Load the RSA private key for signing (admin only).
    
    Reads from LICENSE_PRIVATE_KEY env var. This should NEVER be
    present in distributed builds — only on the developer's machine.
    """
    pem = getattr(app_settings, "LICENSE_PRIVATE_KEY", "")
    if not pem:
        raise RuntimeError(
            "LICENSE_PRIVATE_KEY not configured. "
            "License key generation is only available on the admin machine."
        )
    # Support escaped newlines from .env files
    pem = pem.replace("\\n", "\n")
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    return load_pem_private_key(pem.encode(), password=None)


# Plan definitions
PLANS = {
    PlanType.FREE_TRIAL: {
        "name": "Free Trial",
        "price": 0,
        "duration_days": 10,
        "max_devices": 1,
        "max_users": 5,
        "backup_enabled": False,
        "renewable": False,
        "renewal_price": 0,
    },
    PlanType.OFFLINE_BASIC: {
        "name": "Offline Mode",
        "price": 7999,
        "duration_days": None,  # lifetime
        "max_devices": 1,
        "max_users": 1,
        "backup_enabled": False,
        "renewable": False,
        "renewal_price": 0,
    },
    PlanType.OFFLINE_PREMIUM: {
        "name": "Offline Premium",
        "price": 9999,
        "duration_days": None,  # lifetime
        "max_devices": 1,
        "max_users": 1,
        "backup_enabled": True,
        "renewable": False,
        "renewal_price": 0,
    },
    PlanType.ONLINE: {
        "name": "Online Mode",
        "price": 12999,
        "duration_days": 365,
        "max_devices": 3,
        "max_users": 10,
        "backup_enabled": True,
        "renewable": True,
        "renewal_price": 500,
    },
}


async def get_license() -> Optional[Dict[str, Any]]:
    """Get the current instance's license from DB."""
    collection = await get_collection("license")
    return await collection.find_one({"_id": "instance_license"})


async def get_max_users() -> int:
    """Return the max allowed users for the current license plan."""
    license_doc = await get_license()
    if not license_doc:
        return 1
    return license_doc.get("max_users", 1)


# ── Hardware fingerprint ──────────────────────────────────────────────────────

def get_machine_id() -> str:
    """Generate a stable hardware fingerprint for this machine.
    
    Combines MAC address + platform-specific ID + hostname so it stays
    stable across reboots and is hard to spoof.
    """
    parts = []

    # 1. MAC address
    mac = uuid.getnode()
    if mac:
        parts.append(f"mac:{mac}")

    # 2. Platform-specific machine ID
    system = platform.system()
    try:
        if system == "Linux":
            if os.path.exists("/etc/machine-id"):
                with open("/etc/machine-id") as f:
                    parts.append(f"mid:{f.read().strip()}")
        elif system == "Darwin":
            result = subprocess.run(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                if "IOPlatformUUID" in line:
                    hw_uuid = line.split('"')[-2]
                    parts.append(f"hwuuid:{hw_uuid}")
                    break
        elif system == "Windows":
            result = subprocess.run(
                ["reg", "query", r"HKLM\SOFTWARE\Microsoft\Cryptography", "/v", "MachineGuid"],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                if "MachineGuid" in line:
                    guid = line.strip().split()[-1]
                    parts.append(f"wguid:{guid}")
                    break
    except Exception as e:
        logger.warning(f"Could not read platform machine ID: {e}")

    # 3. Hostname as weak fallback
    parts.append(f"host:{platform.node()}")

    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()


# ── License key signing & verification ────────────────────────────────────────

def _sign_payload(payload: str) -> bytes:
    """Sign a payload string with RSA private key (admin only)."""
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives import hashes
    private_key = _get_private_key()
    return private_key.sign(
        payload.encode(),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )


def _verify_and_decode_key(license_key: str) -> Dict[str, Any]:
    """Decode and verify RSA signature of a license key."""
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives import hashes

    try:
        decoded = base64.b64decode(license_key).decode("utf-8")
    except Exception:
        raise ValueError("Invalid license key format")

    if "|SIG|" not in decoded:
        raise ValueError("Invalid license key — unsigned keys are not accepted")

    payload, sig_b64 = decoded.rsplit("|SIG|", 1)

    try:
        signature = base64.b64decode(sig_b64)
    except Exception:
        raise ValueError("Invalid license key — corrupt signature")

    public_key = _get_public_key()
    try:
        public_key.verify(
            signature,
            payload.encode(),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    except Exception:
        raise ValueError("License key signature is invalid — key may be tampered or forged")

    return json.loads(payload)


async def activate_license(license_key: str, activated_by: str) -> Dict[str, Any]:
    """Activate a license key on this instance. Verifies signature and device binding."""
    data = _verify_and_decode_key(license_key)

    required_fields = ["plan", "customer_name", "issued_at"]
    for field in required_fields:
        if field not in data:
            raise ValueError(f"License key missing field: {field}")

    plan_type = data["plan"]
    if plan_type not in [p.value for p in PlanType]:
        raise ValueError(f"Unknown plan type: {plan_type}")

    plan_info = PLANS[PlanType(plan_type)]

    # Calculate expiry
    issued_at = datetime.fromisoformat(data["issued_at"])
    expires_at = None
    if plan_info["duration_days"]:
        expires_at = issued_at + timedelta(days=plan_info["duration_days"])

    # Bind to this machine
    device_id = get_machine_id()

    # If key has a machine_id baked in, verify it matches this device
    key_machine_id = data.get("machine_id", "")
    if key_machine_id and key_machine_id != device_id:
        raise ValueError("This license key is bound to a different machine. Please contact your administrator for a key generated for this device.")

    license_doc = {
        "_id": "instance_license",
        "license_key": license_key,
        "plan": plan_type,
        "plan_name": plan_info["name"],
        "customer_name": data["customer_name"],
        "customer_email": data.get("customer_email", ""),
        "customer_phone": data.get("customer_phone", ""),
        "max_devices": plan_info["max_devices"],
        "max_users": plan_info.get("max_users", 1),
        "backup_enabled": plan_info["backup_enabled"],
        "issued_at": issued_at,
        "expires_at": expires_at,
        "status": LicenseStatus.ACTIVE.value,
        "devices": [device_id],
        "activated_at": datetime.utcnow(),
        "activated_by": activated_by,
        "renewal_history": [],
    }

    collection = await get_collection("license")
    await collection.replace_one({"_id": "instance_license"}, license_doc, upsert=True)
    logger.info(f"License activated: {plan_type} for {data['customer_name']} on device {device_id[:12]}...")
    return license_doc


async def check_license_status() -> Dict[str, Any]:
    """Check current license validity including device binding."""
    license_doc = await get_license()

    if not license_doc:
        return {"valid": False, "reason": "no_license", "message": "No license activated"}

    # Check suspension
    if license_doc.get("status") == LicenseStatus.SUSPENDED.value:
        return {"valid": False, "reason": "suspended", "message": "License is suspended"}

    # Check expiry
    if license_doc.get("expires_at") and datetime.utcnow() > license_doc["expires_at"]:
        return {
            "valid": False,
            "reason": "expired",
            "message": "License has expired",
            "plan": license_doc["plan"],
            "expired_at": license_doc["expires_at"],
        }

    # Check device binding — is this machine allowed?
    device_id = get_machine_id()
    registered_devices = license_doc.get("devices", [])
    if registered_devices and device_id not in registered_devices:
        max_devices = license_doc.get("max_devices", 1)
        if len(registered_devices) >= max_devices:
            return {
                "valid": False,
                "reason": "device_limit",
                "message": f"This license is bound to another machine. Max {max_devices} device(s) allowed.",
            }
        else:
            # Auto-register if under limit (for online plan with 3 devices)
            collection = await get_collection("license")
            await collection.update_one(
                {"_id": "instance_license"},
                {"$addToSet": {"devices": device_id}}
            )
            logger.info(f"New device auto-registered: {device_id[:12]}...")

    plan_info = PLANS.get(PlanType(license_doc["plan"]), {})
    days_remaining = None
    if license_doc.get("expires_at"):
        days_remaining = (license_doc["expires_at"] - datetime.utcnow()).days

    return {
        "valid": True,
        "plan": license_doc["plan"],
        "plan_name": license_doc.get("plan_name", ""),
        "customer_name": license_doc.get("customer_name", ""),
        "max_devices": license_doc.get("max_devices", 1),
        "max_users": license_doc.get("max_users", 1),
        "backup_enabled": license_doc.get("backup_enabled", False),
        "days_remaining": days_remaining,
        "expires_at": license_doc.get("expires_at"),
        "device_count": len(license_doc.get("devices", [])),
    }


async def register_device(device_id: str) -> bool:
    """Register a device against the license. Returns False if limit exceeded."""
    license_doc = await get_license()
    if not license_doc:
        return False

    devices = license_doc.get("devices", [])
    if device_id in devices:
        return True  # already registered

    max_devices = license_doc.get("max_devices", 1)
    if len(devices) >= max_devices:
        return False

    collection = await get_collection("license")
    await collection.update_one(
        {"_id": "instance_license"},
        {"$addToSet": {"devices": device_id}}
    )
    return True


async def renew_license(renewed_by: str) -> Dict[str, Any]:
    """Renew an online plan license for another year."""
    license_doc = await get_license()
    if not license_doc:
        raise ValueError("No license to renew")

    if license_doc["plan"] != PlanType.ONLINE.value:
        raise ValueError("Only online plan supports renewal")

    current_expiry = license_doc.get("expires_at") or datetime.utcnow()
    # Extend from current expiry (or now if already expired)
    base_date = max(current_expiry, datetime.utcnow())
    new_expiry = base_date + timedelta(days=365)

    collection = await get_collection("license")
    await collection.update_one(
        {"_id": "instance_license"},
        {
            "$set": {
                "expires_at": new_expiry,
                "status": LicenseStatus.ACTIVE.value,
            },
            "$push": {
                "renewal_history": {
                    "renewed_at": datetime.utcnow(),
                    "renewed_by": renewed_by,
                    "previous_expiry": current_expiry,
                    "new_expiry": new_expiry,
                }
            },
        },
    )
    logger.info(f"License renewed until {new_expiry}")
    return {"new_expiry": new_expiry, "days_remaining": (new_expiry - datetime.utcnow()).days}


def generate_license_key(plan: str, customer_name: str, customer_email: str = "",
                         customer_phone: str = "", machine_id: str = "") -> str:
    """Generate an RSA-signed license key. Run on YOUR admin machine only.

    The key = base64( JSON_payload + "|SIG|" + base64(RSA_signature) )
    Nobody can forge this without the private key, even with full source access.
    If machine_id is provided, the key is bound to that specific device.
    """
    data = {
        "plan": plan,
        "customer_name": customer_name,
        "customer_email": customer_email,
        "customer_phone": customer_phone,
        "issued_at": datetime.utcnow().isoformat(),
    }
    if machine_id:
        data["machine_id"] = machine_id
    payload = json.dumps(data, sort_keys=True)
    signature = _sign_payload(payload)
    sig_b64 = base64.b64encode(signature).decode("utf-8")
    signed = payload + "|SIG|" + sig_b64
    return base64.b64encode(signed.encode("utf-8")).decode("utf-8")


# ── Admin operations ──────────────────────────────────────────────────────────

async def extend_trial(extra_days: int, extended_by: str) -> Dict[str, Any]:
    """Extend the trial (or any plan) expiry by N days."""
    license_doc = await get_license()
    if not license_doc:
        raise ValueError("No license found")

    current_expiry = license_doc.get("expires_at")
    if not current_expiry:
        raise ValueError("This plan has no expiry (lifetime license)")

    new_expiry = current_expiry + timedelta(days=extra_days)

    collection = await get_collection("license")
    await collection.update_one(
        {"_id": "instance_license"},
        {
            "$set": {"expires_at": new_expiry, "status": LicenseStatus.ACTIVE.value},
            "$push": {
                "admin_actions": {
                    "action": "extend_trial",
                    "extra_days": extra_days,
                    "previous_expiry": current_expiry,
                    "new_expiry": new_expiry,
                    "performed_by": extended_by,
                    "performed_at": datetime.utcnow(),
                }
            },
        },
    )
    logger.info(f"Trial extended by {extra_days} days → {new_expiry}")
    return {
        "previous_expiry": current_expiry,
        "new_expiry": new_expiry,
        "days_remaining": (new_expiry - datetime.utcnow()).days,
    }


async def suspend_license(reason: str, suspended_by: str) -> Dict[str, Any]:
    """Suspend/stop a license immediately."""
    license_doc = await get_license()
    if not license_doc:
        raise ValueError("No license found")

    collection = await get_collection("license")
    await collection.update_one(
        {"_id": "instance_license"},
        {
            "$set": {"status": LicenseStatus.SUSPENDED.value},
            "$push": {
                "admin_actions": {
                    "action": "suspend",
                    "reason": reason,
                    "performed_by": suspended_by,
                    "performed_at": datetime.utcnow(),
                }
            },
        },
    )
    logger.info(f"License suspended: {reason}")
    return {"status": "suspended", "reason": reason}


async def reactivate_license(reactivated_by: str) -> Dict[str, Any]:
    """Reactivate a suspended license."""
    license_doc = await get_license()
    if not license_doc:
        raise ValueError("No license found")

    if license_doc.get("status") != LicenseStatus.SUSPENDED.value:
        raise ValueError("License is not suspended")

    collection = await get_collection("license")
    await collection.update_one(
        {"_id": "instance_license"},
        {
            "$set": {"status": LicenseStatus.ACTIVE.value},
            "$push": {
                "admin_actions": {
                    "action": "reactivate",
                    "performed_by": reactivated_by,
                    "performed_at": datetime.utcnow(),
                }
            },
        },
    )
    logger.info("License reactivated")
    return {"status": "active"}


async def change_plan(new_plan: str, changed_by: str) -> Dict[str, Any]:
    """Change the license plan (e.g. upgrade from trial to online)."""
    license_doc = await get_license()
    if not license_doc:
        raise ValueError("No license found")

    if new_plan not in [p.value for p in PlanType]:
        raise ValueError(f"Unknown plan: {new_plan}")

    plan_info = PLANS[PlanType(new_plan)]
    old_plan = license_doc.get("plan")

    update_fields = {
        "plan": new_plan,
        "plan_name": plan_info["name"],
        "max_devices": plan_info["max_devices"],
        "max_users": plan_info.get("max_users", 1),
        "backup_enabled": plan_info["backup_enabled"],
        "status": LicenseStatus.ACTIVE.value,
    }

    # Set new expiry based on plan
    if plan_info["duration_days"]:
        update_fields["expires_at"] = datetime.utcnow() + timedelta(days=plan_info["duration_days"])
    else:
        update_fields["expires_at"] = None  # lifetime

    collection = await get_collection("license")
    await collection.update_one(
        {"_id": "instance_license"},
        {
            "$set": update_fields,
            "$push": {
                "admin_actions": {
                    "action": "change_plan",
                    "old_plan": old_plan,
                    "new_plan": new_plan,
                    "performed_by": changed_by,
                    "performed_at": datetime.utcnow(),
                }
            },
        },
    )
    logger.info(f"Plan changed: {old_plan} → {new_plan}")
    return {
        "old_plan": old_plan,
        "new_plan": new_plan,
        "plan_name": plan_info["name"],
        "expires_at": update_fields.get("expires_at"),
    }


async def reset_devices(reset_by: str) -> Dict[str, Any]:
    """Clear all registered devices (useful when customer changes machines)."""
    license_doc = await get_license()
    if not license_doc:
        raise ValueError("No license found")

    old_devices = license_doc.get("devices", [])
    collection = await get_collection("license")
    await collection.update_one(
        {"_id": "instance_license"},
        {
            "$set": {"devices": []},
            "$push": {
                "admin_actions": {
                    "action": "reset_devices",
                    "cleared_devices": old_devices,
                    "performed_by": reset_by,
                    "performed_at": datetime.utcnow(),
                }
            },
        },
    )
    logger.info(f"Devices reset — cleared {len(old_devices)} devices")
    return {"cleared": len(old_devices)}


async def get_admin_log() -> list:
    """Get the admin action history for this license."""
    license_doc = await get_license()
    if not license_doc:
        return []
    return license_doc.get("admin_actions", [])


# ── Backup & Restore ──────────────────────────────────────────────────────────

BACKUP_DIR = os.path.join(
    os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
    else os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "backups"
)


async def create_backup(created_by: str = "system") -> Dict[str, Any]:
    """Create a full MongoDB backup as a zip archive.
    
    Requires mongodump to be installed on the system.
    Only allowed if the license plan has backup_enabled=True.
    """
    license_doc = await get_license()
    if not license_doc:
        raise ValueError("No license found")
    if not license_doc.get("backup_enabled"):
        raise ValueError("Backup is not enabled on your plan. Upgrade to Offline Premium or Online.")

    # Ensure backup directory exists
    os.makedirs(BACKUP_DIR, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    db_name = app_settings.DATABASE_NAME
    dump_dir = os.path.join(BACKUP_DIR, f"dump_{timestamp}")
    zip_path = os.path.join(BACKUP_DIR, f"backup_{db_name}_{timestamp}")

    # Build mongodump command
    mongo_url = app_settings.MONGODB_URL
    cmd = ["mongodump", f"--uri={mongo_url}", f"--db={db_name}", f"--out={dump_dir}"]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(f"mongodump failed: {result.stderr}")
    except FileNotFoundError:
        raise RuntimeError("mongodump not found. Install MongoDB Database Tools to enable backups.")

    # Zip the dump
    zip_file = shutil.make_archive(zip_path, "zip", dump_dir)

    # Clean up raw dump directory
    shutil.rmtree(dump_dir, ignore_errors=True)

    file_size = os.path.getsize(zip_file)
    logger.info(f"Backup created: {zip_file} ({file_size} bytes) by {created_by}")

    return {
        "filename": os.path.basename(zip_file),
        "path": zip_file,
        "size_bytes": file_size,
        "created_at": datetime.utcnow().isoformat(),
        "created_by": created_by,
    }


async def restore_backup(filename: str, restored_by: str = "system") -> Dict[str, Any]:
    """Restore a MongoDB backup from a zip archive.
    
    Requires mongorestore to be installed on the system.
    """
    license_doc = await get_license()
    if not license_doc:
        raise ValueError("No license found")
    if not license_doc.get("backup_enabled"):
        raise ValueError("Backup/restore is not enabled on your plan.")

    zip_path = os.path.join(BACKUP_DIR, filename)
    if not os.path.exists(zip_path):
        raise ValueError(f"Backup file not found: {filename}")

    # Validate it's actually inside BACKUP_DIR (prevent path traversal)
    real_backup_dir = os.path.realpath(BACKUP_DIR)
    real_zip_path = os.path.realpath(zip_path)
    if not real_zip_path.startswith(real_backup_dir):
        raise ValueError("Invalid backup file path")

    db_name = app_settings.DATABASE_NAME
    mongo_url = app_settings.MONGODB_URL
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    extract_dir = os.path.join(BACKUP_DIR, f"restore_{timestamp}")

    try:
        # Extract zip
        shutil.unpack_archive(zip_path, extract_dir)

        # Find the database folder inside the extracted dump
        dump_path = os.path.join(extract_dir, db_name)
        if not os.path.isdir(dump_path):
            # Try to find it one level deeper
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
        raise RuntimeError("mongorestore not found. Install MongoDB Database Tools to enable restore.")
    finally:
        shutil.rmtree(extract_dir, ignore_errors=True)

    logger.info(f"Backup restored: {filename} by {restored_by}")
    return {
        "filename": filename,
        "restored_at": datetime.utcnow().isoformat(),
        "restored_by": restored_by,
    }


def list_backups() -> list:
    """List all available backup zip files."""
    if not os.path.exists(BACKUP_DIR):
        return []

    backups = []
    for f in sorted(os.listdir(BACKUP_DIR), reverse=True):
        if f.endswith(".zip") and f.startswith("backup_"):
            filepath = os.path.join(BACKUP_DIR, f)
            stat = os.stat(filepath)
            backups.append({
                "filename": f,
                "size_bytes": stat.st_size,
                "created_at": datetime.utcfromtimestamp(stat.st_mtime).isoformat(),
            })
    return backups
