from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel

from models.shipment import ShipmentStatus


# ── Customer ──────────────────────────────────────────────────────────────────

class CustomerCreate(BaseModel):
    first_name: str
    last_name: str
    phone_number: str
    address: str


class CustomerUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone_number: Optional[str] = None
    address: Optional[str] = None


class CustomerResponse(BaseModel):
    id: str
    first_name: str
    last_name: str
    phone_number: str
    address: str

    model_config = {"from_attributes": True}


# ── Package ───────────────────────────────────────────────────────────────────

class PackageCreate(BaseModel):
    shipment_id: str
    description: str
    weight_kg: Decimal
    declared_value: Decimal


class PackageUpdate(BaseModel):
    description: Optional[str] = None
    weight_kg: Optional[Decimal] = None
    declared_value: Optional[Decimal] = None


class PackageResponse(BaseModel):
    id: str
    shipment_id: str
    description: str
    weight_kg: Decimal
    declared_value: Decimal

    model_config = {"from_attributes": True}


# ── Shipment ──────────────────────────────────────────────────────────────────

class ShipmentCreate(BaseModel):
    customer_id: str
    tracking_number: str
    status: ShipmentStatus
    carrier: str
    origin: str
    destination: str
    estimated_delivery: date


class ShipmentUpdate(BaseModel):
    tracking_number: Optional[str] = None
    status: Optional[ShipmentStatus] = None
    carrier: Optional[str] = None
    origin: Optional[str] = None
    destination: Optional[str] = None
    estimated_delivery: Optional[date] = None


class ShipmentResponse(BaseModel):
    id: str
    customer_id: str
    tracking_number: str
    status: ShipmentStatus
    carrier: str
    origin: str
    destination: str
    estimated_delivery: date
    last_update: datetime
    packages: list[PackageResponse] = []

    model_config = {"from_attributes": True}
