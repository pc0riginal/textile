from datetime import datetime
from fastapi import Request
from app.database import get_collection

class AuditService:
    @staticmethod
    async def log_activity(company_id: str, user_id: str, username: str, action: str, entity_type: str, ip_address: str = None, entity_id: str = None, details: dict = None):
        audit_collection = await get_collection("audit_logs")
        await audit_collection.insert_one({
            "company_id": company_id,
            "user_id": user_id,
            "username": username,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "ip_address": ip_address,
            "details": details,
            "timestamp": datetime.utcnow()
        })
    
    @staticmethod
    def get_client_ip(request: Request) -> str:
        return request.client.host if request.client else "unknown"
