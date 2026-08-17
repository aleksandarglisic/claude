"""
Admin routes — full CRUD for customers, shipments, and packages (Epic E2, E3).
Every endpoint is protected by require_admin (Auth0 JWT validation).
The two identity systems never intersect: no path here touches ChatSession.state.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from auth.auth0 import require_admin
from db.session import get_db
from models.customer import Customer
from models.package import Package
from models.shipment import Shipment
from schemas.admin import (
    CustomerCreate,
    CustomerResponse,
    CustomerUpdate,
    PackageCreate,
    PackageResponse,
    PackageUpdate,
    ShipmentCreate,
    ShipmentResponse,
    ShipmentUpdate,
)

router = APIRouter(prefix="/admin", tags=["admin"])


# ── Identity check ────────────────────────────────────────────────────────────

@router.get("/me")
async def admin_me(payload: dict = Depends(require_admin)) -> dict:
    return {
        "sub": payload.get("sub"),
        "email": payload.get("email"),
        "name": payload.get("name"),
    }


# ── Customers ─────────────────────────────────────────────────────────────────

@router.get("/customers", response_model=list[CustomerResponse])
async def list_customers(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
) -> list[CustomerResponse]:
    result = await db.execute(select(Customer).order_by(Customer.last_name, Customer.first_name))
    return result.scalars().all()


@router.post("/customers", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(
    body: CustomerCreate,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
) -> CustomerResponse:
    customer = Customer(id=str(uuid.uuid4()), **body.model_dump())
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    return customer


@router.get("/customers/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: str,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
) -> CustomerResponse:
    customer = await db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


@router.put("/customers/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: str,
    body: CustomerUpdate,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
) -> CustomerResponse:
    customer = await db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(customer, field, value)
    await db.commit()
    await db.refresh(customer)
    return customer


@router.delete("/customers/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer(
    customer_id: str,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
) -> None:
    customer = await db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    await db.delete(customer)
    await db.commit()


# ── Shipments ─────────────────────────────────────────────────────────────────

@router.get("/shipments", response_model=list[ShipmentResponse])
async def list_shipments(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
) -> list[ShipmentResponse]:
    result = await db.execute(
        select(Shipment)
        .options(selectinload(Shipment.packages))
        .order_by(Shipment.last_update.desc())
    )
    return result.scalars().all()


@router.post("/shipments", response_model=ShipmentResponse, status_code=status.HTTP_201_CREATED)
async def create_shipment(
    body: ShipmentCreate,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
) -> ShipmentResponse:
    customer = await db.get(Customer, body.customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    shipment = Shipment(id=str(uuid.uuid4()), **body.model_dump())
    db.add(shipment)
    await db.commit()
    result = await db.execute(
        select(Shipment).options(selectinload(Shipment.packages)).where(Shipment.id == shipment.id)
    )
    return result.scalar_one()


@router.get("/shipments/{shipment_id}", response_model=ShipmentResponse)
async def get_shipment(
    shipment_id: str,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
) -> ShipmentResponse:
    result = await db.execute(
        select(Shipment).options(selectinload(Shipment.packages)).where(Shipment.id == shipment_id)
    )
    shipment = result.scalar_one_or_none()
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return shipment


@router.put("/shipments/{shipment_id}", response_model=ShipmentResponse)
async def update_shipment(
    shipment_id: str,
    body: ShipmentUpdate,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
) -> ShipmentResponse:
    result = await db.execute(
        select(Shipment).options(selectinload(Shipment.packages)).where(Shipment.id == shipment_id)
    )
    shipment = result.scalar_one_or_none()
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(shipment, field, value)
    await db.commit()
    await db.refresh(shipment)
    result = await db.execute(
        select(Shipment).options(selectinload(Shipment.packages)).where(Shipment.id == shipment_id)
    )
    return result.scalar_one()


@router.delete("/shipments/{shipment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shipment(
    shipment_id: str,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
) -> None:
    shipment = await db.get(Shipment, shipment_id)
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")
    await db.delete(shipment)
    await db.commit()


# ── Packages ──────────────────────────────────────────────────────────────────

@router.get("/packages", response_model=list[PackageResponse])
async def list_packages(
    shipment_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
) -> list[PackageResponse]:
    q = select(Package)
    if shipment_id:
        q = q.where(Package.shipment_id == shipment_id)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/packages", response_model=PackageResponse, status_code=status.HTTP_201_CREATED)
async def create_package(
    body: PackageCreate,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
) -> PackageResponse:
    shipment = await db.get(Shipment, body.shipment_id)
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")
    package = Package(id=str(uuid.uuid4()), **body.model_dump())
    db.add(package)
    await db.commit()
    await db.refresh(package)
    return package


@router.get("/packages/{package_id}", response_model=PackageResponse)
async def get_package(
    package_id: str,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
) -> PackageResponse:
    package = await db.get(Package, package_id)
    if not package:
        raise HTTPException(status_code=404, detail="Package not found")
    return package


@router.put("/packages/{package_id}", response_model=PackageResponse)
async def update_package(
    package_id: str,
    body: PackageUpdate,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
) -> PackageResponse:
    package = await db.get(Package, package_id)
    if not package:
        raise HTTPException(status_code=404, detail="Package not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(package, field, value)
    await db.commit()
    await db.refresh(package)
    return package


@router.delete("/packages/{package_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_package(
    package_id: str,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
) -> None:
    package = await db.get(Package, package_id)
    if not package:
        raise HTTPException(status_code=404, detail="Package not found")
    await db.delete(package)
    await db.commit()
