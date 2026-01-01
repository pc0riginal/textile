from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime
from app.models.company import Address, Contact

class PartyCreate(BaseModel):
    name: str
    party_type: str  # customer, supplier, both, broker, transporter
    party_code: Optional[str] = None
    gstin: Optional[str] = None
    pan: Optional[str] = None
    address: Address
    contact: Contact
    credit_limit: float = 0.0
    opening_balance: float = 0.0

class Party(BaseModel):
    id: Optional[str] = None
    company_id: str
    name: str
    party_type: str
    party_code: Optional[str] = None
    gstin: Optional[str] = None
    pan: Optional[str] = None
    address: Address
    contact: Contact
    credit_limit: float = 0.0
    opening_balance: float = 0.0
    current_balance: float = 0.0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }