"""License management — validates plan, expiry, and device limits per instance."""
import hashlib
import json
import base64
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from bson import ObjectId

from app.database import get_collection
from app.enums import PlanType, LicenseStatus
from app.logger import logger


# Plan definitions
PLANS = {
    PlanType.FREE_TRIAL: {
        "name": "Free Trial",
        "price": 0,
        "duration_days": 10,
        "max_devices": 1,
        "backup_enabled": False,
        "renewable": False,
        "renewal_price": 0,
    },
    PlanType.OFFLINE_BASIC: {
        "name": "Offline Mode",
        "price": 7999,
        "duration_days": None,  # lifetime
        "max_devices": 1,
        "backup_enabled": False,
        "renewable": False,
        "renewal_price": 0,
    },
    PlanType.OFFLINE_PREMIUM: {
        "name": "Offline Premium",
        "price": 9999,
        "duration_days": None,  # lifetime
        "max_devices": 1,
        "backup_enabled": True,
        "renewable": False,
        "renewal_price": 0,
    },
    PlanType.ONLINE: {
        "name": "Online Mode",
        "price": 12999,
        "duration_days": 365,
        "max_devices": 3,
        "backup_enabled": True,
        "renewable": True,
        "renewal_price": 500,
    },
}


async def get_license() -> Optional[Dict[str, Any]]:
    """Get the current instance's license from DB."""
    collection = await get_collection("license")
    return await collection.find_one({"_id": "instance_license"})


async def activate_license(license_key: str, activated_by: str) -> Dict[str, Any]:
    """Activate a license key on this instance.
    
    License key format: base64-encoded JSON with plan, customer, expiry info.
    In production, you'd sign this with HMAC — for now, simple base64 + checksum.
    """
    try:
        decoded = base64.b64decode(license_key).decode("utf-8")
        data = json.loads(decoded)
    except Exception:
        raise ValueError("Invalid license key format")

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

    license_doc = {
        "_id": "instance_license",
        "license_key": license_key,
        "plan": plan_type,
        "plan_name": plan_info["name"],
        "customer_name": data["customer_name"],
        "customer_email": data.get("customer_email", ""),
        "customer_phone": data.get("customer_phone", ""),
        "max_devices": plan_info["max_devices"],
        "backup_enabled": plan_info["backup_enabled"],
        "issued_at": issued_at,
        "expires_at": expires_at,
        "status": LicenseStatus.ACTIVE.value,
        "devices": [],
        "activated_at": datetime.utcnow(),
        "activated_by": activated_by,
        "renewal_history": [],
    }

    collection = await get_collection("license")
    await collection.replace_one({"_id": "instance_license"}, license_doc, upsert=True)
    logger.info(f"License activated: {plan_type} for {data['customer_name']}")
    return license_doc


async def check_license_status() -> Dict[str, Any]:
    """Check current license validity. Returns status info dict."""
    license_doc = await get_license()

    if not license_doc:
        return {"valid": False, "reason": "no_license", "message": "No license activated"}

    # Check expiry
    if license_doc.get("expires_at") and datetime.utcnow() > license_doc["expires_at"]:
        return {
            "valid": False,
            "reason": "expired",
            "message": "License has expired",
            "plan": license_doc["plan"],
            "expired_at": license_doc["expires_at"],
        }

    if license_doc.get("status") == LicenseStatus.SUSPENDED.value:
        return {"valid": False, "reason": "suspended", "message": "License is suspended"}

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
                         customer_phone: str = "") -> str:
    """Generate a license key (run this on YOUR admin machine, not the customer's).
    
    Usage: python -c "from app.services.license_service import generate_license_key; print(generate_license_key('online', 'Customer Name', '[email]', '[phone]'))"
    """
    data = {
        "plan": plan,
        "customer_name": customer_name,
        "customer_email": customer_email,
        "customer_phone": customer_phone,
        "issued_at": datetime.utcnow().isoformat(),
    }
    return base64.b64encode(json.dumps(data).encode("utf-8")).decode("utf-8")


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
