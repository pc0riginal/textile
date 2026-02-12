from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import datetime
from bson import ObjectId


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    full_name: str


class UserLogin(BaseModel):
    username: str
    password: str


class User(BaseModel):
    id: Optional[str] = None
    username: str
    email: EmailStr
    full_name: str
    is_active: bool = True
    companies: List[str] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        json_encoders = {
            ObjectId: str,
            datetime: lambda v: v.isoformat()
        }
