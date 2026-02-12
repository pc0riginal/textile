"""Enums for consistent string constants across the application."""
from enum import Enum


class PartyType(str, Enum):
    CUSTOMER = "customer"
    SUPPLIER = "supplier"
    BOTH = "both"
    BROKER = "broker"
    TRANSPORTER = "transporter"


class PaymentType(str, Enum):
    RECEIPT = "receipt"
    CHEQUE = "cheque"
    CASH = "cash"
    NEFT = "neft"
    RTGS = "rtgs"


class PaymentStatus(str, Enum):
    UNPAID = "unpaid"
    PARTIAL = "partial"
    PAID = "paid"
    COMPLETED = "completed"


class DocumentStatus(str, Enum):
    DRAFT = "draft"
    FINALIZED = "finalized"
    CANCELLED = "cancelled"


class AuditAction(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    LOGIN = "login"
    LOGOUT = "logout"


class TransactionType(str, Enum):
    CREDIT = "credit"
    DEBIT = "debit"


class PlanType(str, Enum):
    FREE_TRIAL = "free_trial"
    OFFLINE_BASIC = "offline_basic"
    OFFLINE_PREMIUM = "offline_premium"
    ONLINE = "online"


class LicenseStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    SUSPENDED = "suspended"
