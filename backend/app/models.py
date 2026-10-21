"""SQLAlchemy ORM models for the plain-CRUD tables.

The schema itself is owned by db/01_schema.sql — these classes only map to
it (no create_all). Tables whose logic lives in SQL (appointments, doctors'
geography column, reviews, reminders) are accessed with raw SQL instead.
"""
import uuid
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, SmallInteger, Text, Time, text
from sqlalchemy.dialects.postgresql import ARRAY, DATERANGE, ENUM, TIMESTAMP, UUID, Range
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

MealTypeEnum = ENUM("breakfast", "lunch", "dinner", "snack", name="meal_type", create_type=False)


class Base(DeclarativeBase):
    pass


def uuid_pk():
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))


def created_at():
    return mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))


class Specialty(Base):
    __tablename__ = "specialties"
    specialty_id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)


class Patient(Base):
    __tablename__ = "patients"
    patient_id: Mapped[uuid.UUID] = uuid_pk()
    full_name: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(Text, unique=True)
    phone: Mapped[str | None] = mapped_column(Text)
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    dietary_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at()


class Medication(Base):
    __tablename__ = "medications"
    medication_id: Mapped[uuid.UUID] = uuid_pk()
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.patient_id"))
    drug_name: Mapped[str] = mapped_column(Text)
    dosage: Mapped[str] = mapped_column(Text)
    active_range: Mapped[Range[date]] = mapped_column(DATERANGE)
    created_at: Mapped[datetime] = created_at()

    reminders: Mapped[list["MedicationReminder"]] = relationship(
        back_populates="medication", cascade="all, delete-orphan", passive_deletes=True,
        order_by="MedicationReminder.reminder_time")


class MedicationReminder(Base):
    __tablename__ = "medication_reminders"
    medication_reminder_id: Mapped[uuid.UUID] = uuid_pk()
    medication_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("medications.medication_id", ondelete="CASCADE"))
    reminder_time: Mapped[time] = mapped_column(Time)
    days_of_week: Mapped[list[int]] = mapped_column(ARRAY(SmallInteger), server_default=text("'{0,1,2,3,4,5,6}'"))
    label: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at()

    medication: Mapped[Medication] = relationship(back_populates="reminders")


class Meal(Base):
    __tablename__ = "meals"
    meal_id: Mapped[uuid.UUID] = uuid_pk()
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.patient_id"))
    meal_date: Mapped[date] = mapped_column(Date)
    meal_type: Mapped[str] = mapped_column(MealTypeEnum)
    description: Mapped[str] = mapped_column(Text)
    calories: Mapped[int | None] = mapped_column(Integer)
    is_planned: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = created_at()


class WellnessLog(Base):
    __tablename__ = "wellness_logs"
    log_id: Mapped[uuid.UUID] = uuid_pk()
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.patient_id"))
    log_date: Mapped[date] = mapped_column(Date)
    mood_score: Mapped[int | None] = mapped_column(SmallInteger)
    sleep_hours: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    water_intake_ml: Mapped[int | None] = mapped_column(Integer)


class DiaryEntry(Base):
    __tablename__ = "diary_entries"
    entry_id: Mapped[uuid.UUID] = uuid_pk()
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.patient_id", ondelete="CASCADE"))
    entry_date: Mapped[date] = mapped_column(Date, server_default=text("CURRENT_DATE"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))
