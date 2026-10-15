from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))  # publisher | advertiser | admin
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    listings: Mapped[list["Listing"]] = relationship(
        back_populates="publisher", cascade="all, delete-orphan"
    )


class Listing(Base):
    __tablename__ = "listings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    publisher_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    site_name: Mapped[str] = mapped_column(String(200))
    site_url: Mapped[str] = mapped_column(String(500))
    niche: Mapped[str] = mapped_column(String(100))
    price_usd: Mapped[float] = mapped_column(Float)
    turnaround_days: Mapped[int] = mapped_column(Integer)
    guidelines: Mapped[str] = mapped_column(Text, default="")
    da_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    publisher: Mapped["User"] = relationship(back_populates="listings")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"))
    advertiser_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    publisher_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    brief: Mapped[str] = mapped_column(Text)
    target_url: Mapped[str] = mapped_column(String(500))
    anchor_text: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="requested")
    mock_payment_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    listing: Mapped["Listing"] = relationship()
    advertiser: Mapped["User"] = relationship(foreign_keys=[advertiser_id])
    publisher: Mapped["User"] = relationship(foreign_keys=[publisher_id])


class EmailLog(Base):
    __tablename__ = "email_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    to_email: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    related_order_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
