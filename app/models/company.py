from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import datetime

class Address(BaseModel):
    line1: str
    line2: Optional[str] = None
    city: str
    state: str
    pincode: str

class Contact(BaseModel):
    phone: str
    email: Optional[EmailStr] = None
    website: Optional[str] = None

class BankDetail(BaseModel):
    bank_name: str
    account_no: str
    ifsc: str
    branch: str

class CompanyCreate(BaseModel):
    name: str
    gstin: Optional[str] = None
    pan: Optional[str] = None
    address: Address
    contact: Contact
    bank_details: List[BankDetail] = []
    financial_year: str = None
    invoice_series: str = "INV"
    challan_series: str = "CH"

class Company(BaseModel):
    id: Optional[str] = None
    name: str
    gstin: Optional[str] = None
    pan: Optional[str] = None
    address: Address
    contact: Contact
    bank_details: List[BankDetail] = []
    logo_url: Optional[str] = None
    financial_year: str
    invoice_series: str
    challan_series: str
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }