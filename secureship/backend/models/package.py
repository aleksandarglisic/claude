import uuid
from decimal import Decimal
from sqlalchemy import String, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db.session import Base


class Package(Base):
    __tablename__ = "packages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    shipment_id: Mapped[str] = mapped_column(String, ForeignKey("shipments.id"), nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    declared_value: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    shipment: Mapped["Shipment"] = relationship("Shipment", back_populates="packages")
