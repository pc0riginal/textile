from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class BankAccount(BaseModel):
    account_name: str
    account_number: str
    bank_name: str
    branch: Optional[str] = None
    ifsc_code: str
    account_type: str = "Current"
    opening_balance: float = 0.0
    current_balance: float = 0.0
    is_active: bool = True
    company_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
