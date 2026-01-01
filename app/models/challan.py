from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

class ChallanItem(BaseModel):
    quality: str
    boxes: int
    meters_per_box: float
    total_meters: float
    weight: Optional[float] = 0.0
    rate_per_meter: float
    amount: float

class AuditLog(BaseModel):
    action: str
    user_id: str
    timestamp: datetime
    changes: Dict[str, Any] = {}

class PurchaseChallanCreate(BaseModel):
    supplier_id: str
    challan_date: datetime
    items: List[ChallanItem]
    broker_id: Optional[str] = None
    brokerage: float = 0.0
    transporter_id: Optional[str] = None
    freight: float = 0.0
    payment_terms: Optional[str] = None
    notes: Optional[str] = None

class PurchaseChallan(BaseModel):
    id: Optional[str] = None
    company_id: str
    challan_no: str
    challan_date: datetime
    supplier_id: str
    supplier_name: str
    financial_year: str
    items: List[ChallanItem]
    broker_id: Optional[str] = None
    brokerage: float = 0.0
    transporter_id: Optional[str] = None
    freight: float = 0.0
    
    # Calculated fields
    taxable_amount: float = 0.0
    cgst: float = 0.0
    sgst: float = 0.0
    igst: float = 0.0
    tcs: float = 0.0
    tds: float = 0.0
    total_amount: float = 0.0
    
    # Inventory tracking (CRITICAL)
    total_boxes: int = 0
    total_meters: float = 0.0
    available_boxes: int = 0
    available_meters: float = 0.0
    transferred_boxes: int = 0
    transferred_meters: float = 0.0
    
    # Transfer tracking
    is_transfer_source: bool = False
    is_received_via_transfer: bool = False
    transfer_source_id: Optional[str] = None
    transfer_reference: Optional[str] = None
    
    payment_terms: Optional[str] = None
    notes: Optional[str] = None
    attachments: List[str] = []
    status: str = "draft"  # draft, finalized, cancelled
    
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    audit_log: List[AuditLog] = []

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }