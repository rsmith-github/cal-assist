from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Day(Base):
    __tablename__ = "days"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_days_user_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    total_calories_in: Mapped[int] = mapped_column(Integer, default=0)
    total_calories_out: Mapped[int] = mapped_column(Integer, default=0)
    net_calories: Mapped[int] = mapped_column(Integer, default=0)
    closed: Mapped[bool] = mapped_column(Boolean, default=False)

    entries: Mapped[list["Entry"]] = relationship(
        "Entry", back_populates="day", order_by="Entry.timestamp"
    )


class Entry(Base):
    __tablename__ = "entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    day_id: Mapped[int] = mapped_column(Integer, ForeignKey("days.id"), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(String(512), nullable=False)
    parsed_name: Mapped[str] = mapped_column(String(256), default="")
    calories_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    calories_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
    )
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)

    day: Mapped["Day"] = relationship("Day", back_populates="entries")
