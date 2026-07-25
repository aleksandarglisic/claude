import uuid
import enum
from datetime import date, datetime
from sqlalchemy import String, ForeignKey, Enum as SAEnum, Date, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db.session import Base


class ShipmentStatus(str, enum.Enum):
    label_created = "label_created"
    in_transit = "in_transit"
    out_for_delivery = "out_for_delivery"
    delivered = "delivered"
    exception = "exception"


class Shipment(Base):
    __tablename__ = "shipments"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    customer_id: Mapped[str] = mapped_column(String, ForeignKey("customers.id"), nullable=False)
    tracking_number: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    status: Mapped[ShipmentStatus] = mapped_column(SAEnum(ShipmentStatus), nullable=False)
    carrier: Mapped[str] = mapped_column(String, nullable=False)
    origin: Mapped[str] = mapped_column(String, nullable=False)
    destination: Mapped[str] = mapped_column(String, nullable=False)
    estimated_delivery: Mapped[date] = mapped_column(Date, nullable=False)
    last_update: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    customer: Mapped["Customer"] = relationship("Customer", back_populates="shipments")
    packages: Mapped[list["Package"]] = relationship("Package", back_populates="shipment")
