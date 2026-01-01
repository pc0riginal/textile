from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class TransferRecipient(BaseModel):
    party_id: str
    party_name: str
    boxes: int
    meters: float
    created_challan_id: Optional[str] = None
    created_challan_no: Optional[str] = None

class InventoryTransferCreate(BaseModel):
    source_challan_id: str
    transfer_date: datetime
    quality: str
    boxes_transferred: int
    meters_transferred: float
    recipients: List[TransferRecipient]
    reason: Optional[str] = None
    notes: Optional[str] = None

class InventoryTransfer(BaseModel):
    id: Optional[str] = None
    company_id: str
    transfer_no: str
    transfer_date: datetime
    
    # Source details
    source_challan_id: str
    source_challan_no: str
    source_party_id: str
    source_party_name: str
    
    # Transfer details
    quality: str
    boxes_transferred: int
    meters_transferred: float
    
    # Recipients
    recipients: List[TransferRecipient]
    
    reason: Optional[str] = None
    notes: Optional[str] = None
    status: str = "completed"  # completed, cancelled
    
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    
    # Reversal tracking
    is_reversed: bool = False
    reversed_at: Optional[datetime] = None
    reversed_by: Optional[str] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }