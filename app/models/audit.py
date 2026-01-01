from pydantic import BaseModel
from typing import Dict, Any, Optional
from datetime import datetime

class AuditLogCreate(BaseModel):
    action: str  # create, update, delete, login, logout
    entity_type: str  # invoice, challan, payment, etc.
    entity_id: Optional[str] = None
    changes: Dict[str, Any] = {}
    ip_address: Optional[str] = None

class AuditLog(BaseModel):
    id: Optional[str] = None
    company_id: str
    user_id: str
    username: str
    action: str
    entity_type: str
    entity_id: Optional[str] = None
    changes: Dict[str, Any] = {}
    ip_address: Optional[str] = None
    timestamp: datetime

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }