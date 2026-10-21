"""Pydantic request / response models."""
from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

AppointmentStatus = Literal["scheduled", "completed", "cancelled", "no_show"]
MealType = Literal["breakfast", "lunch", "dinner", "snack"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------- specialties ----------------
class SpecialtyIn(BaseModel):
    name: str = Field(min_length=2, examples=["Rheumatologist"])


class SpecialtyOut(ORM):
    specialty_id: int
    name: str
    doctor_count: int | None = None


# ---------------- patients ----------------
class PatientIn(BaseModel):
    full_name: str = Field(min_length=2)
    email: EmailStr
    phone: str | None = None
    date_of_birth: date | None = None
    dietary_notes: str | None = Field(None, examples=["Vegetarian, lactose intolerant"])


class PatientUpdate(BaseModel):
    full_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    date_of_birth: date | None = None
    dietary_notes: str | None = None


class PatientOut(ORM):
    patient_id: UUID
    full_name: str
    email: str
    phone: str | None
    date_of_birth: date | None
    dietary_notes: str | None
    created_at: datetime


# ---------------- doctors ----------------
class ScheduleBlock(BaseModel):
    day_of_week: int = Field(ge=0, le=6, description="0=Sunday .. 6=Saturday")
    start_time: time
    end_time: time
    slot_minutes: int = Field(30, gt=0, le=240)

    @model_validator(mode="after")
    def check_order(self):
        if self.start_time >= self.end_time:
            raise ValueError("start_time must be before end_time")
        return self


class DoctorIn(BaseModel):
    full_name: str
    email: EmailStr
    phone: str | None = None
    specialty_id: int
    consultation_fee: Decimal = Field(ge=0)
    latitude: float = Field(ge=-90, le=90, examples=[19.0596])
    longitude: float = Field(ge=-180, le=180, examples=[72.8295])
    address_text: str | None = None
    schedule: list[ScheduleBlock] = []


class DoctorOut(BaseModel):
    doctor_id: UUID
    full_name: str
    email: str
    phone: str | None
    specialty_id: int
    specialty: str
    consultation_fee: Decimal
    latitude: float
    longitude: float
    address_text: str | None
    average_rating: Decimal
    rating_count: int
    created_at: datetime


class DoctorDetail(DoctorOut):
    schedule: list[ScheduleBlock]
    profile: DoctorProfileOut | None = None


class RankedDoctor(BaseModel):
    doctor_id: UUID
    full_name: str
    specialty: str
    address_text: str | None
    consultation_fee: Decimal
    average_rating: Decimal
    rating_count: int
    distance_km: Decimal
    distance_score: Decimal
    fee_score: Decimal
    rating_score: Decimal
    composite_score: Decimal
    next_available: datetime | None = None


class UnavailabilityIn(BaseModel):
    start_at: datetime
    end_at: datetime
    reason: str | None = Field(None, examples=["Medical conference"])

    @model_validator(mode="after")
    def check_order(self):
        if self.start_at >= self.end_at:
            raise ValueError("start_at must be before end_at")
        return self


class UnavailabilityOut(BaseModel):
    unavailability_id: UUID
    start_at: datetime
    end_at: datetime
    reason: str | None
    affected_appointments: int | None = None


class Slot(BaseModel):
    slot_start: datetime
    slot_end: datetime


# ---------------- appointments ----------------
class AppointmentIn(BaseModel):
    patient_id: UUID
    doctor_id: UUID
    start_at: datetime = Field(description="Slot start, e.g. 2026-10-05T10:30:00+05:30")


class AppointmentOut(BaseModel):
    appointment_id: UUID
    patient_id: UUID
    patient_name: str | None = None
    doctor_id: UUID
    doctor_name: str | None = None
    specialty: str | None = None
    start_at: datetime
    end_at: datetime
    status: AppointmentStatus
    created_at: datetime
    has_review: bool | None = None


# ---------------- reviews ----------------
class ReviewIn(BaseModel):
    appointment_id: UUID
    patient_id: UUID = Field(description="The patient writing the review (must match the appointment)")
    rating: int = Field(ge=1, le=5)
    comment: str | None = None


class ReviewOut(BaseModel):
    review_id: UUID
    appointment_id: UUID
    patient_id: UUID
    patient_name: str | None = None
    doctor_id: UUID
    rating: int
    comment: str | None
    created_at: datetime


# ---------------- reminders ----------------
class ReminderOut(BaseModel):
    reminder_id: UUID
    appointment_id: UUID
    remind_at: datetime
    sent_at: datetime | None
    patient_name: str | None = None
    doctor_name: str | None = None
    appointment_start: datetime | None = None


# ---------------- medications ----------------
class MedReminderIn(BaseModel):
    reminder_time: time = Field(examples=["08:00"])
    days_of_week: list[int] = Field(default=[0, 1, 2, 3, 4, 5, 6], description="0=Sun..6=Sat")
    label: str | None = Field(None, examples=["Morning dose"])

    @field_validator("days_of_week")
    @classmethod
    def valid_days(cls, v):
        if not v or any(d < 0 or d > 6 for d in v):
            raise ValueError("days_of_week must be a non-empty list of 0..6")
        return sorted(set(v))


class MedReminderOut(ORM):
    medication_reminder_id: UUID
    reminder_time: time
    days_of_week: list[int]
    label: str | None


class MedicationIn(BaseModel):
    drug_name: str = Field(examples=["Amoxicillin 500mg"])
    dosage: str = Field(examples=["1 capsule three times daily"])
    start_date: date
    end_date: date | None = Field(None, description="Exclusive: first day NOT taken. null = ongoing")
    reminders: list[MedReminderIn] = []

    @model_validator(mode="after")
    def check_range(self):
        if self.end_date is not None and self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        return self


class MedicationUpdate(BaseModel):
    dosage: str | None = None
    end_date: date | None = None
    make_ongoing: bool = Field(False, description="Set true to clear end_date")


class MedicationOut(BaseModel):
    medication_id: UUID
    patient_id: UUID
    drug_name: str
    dosage: str
    start_date: date
    end_date: date | None
    is_active_today: bool
    reminders: list[MedReminderOut]
    created_at: datetime


class OverlapOut(BaseModel):
    medication_a_id: UUID
    drug_a: str
    medication_b_id: UUID
    drug_b: str
    overlap_start: date
    overlap_end: date | None
    overlap_days: int | None


class MedicationCreated(MedicationOut):
    overlaps: list[OverlapOut] = Field(description="Existing prescriptions whose dates overlap (informational)")


class DoseOut(BaseModel):
    log_id: UUID | None
    medication_reminder_id: UUID
    medication_id: UUID
    drug_name: str
    dosage: str
    reminder_time: time
    label: str | None
    sent_at: datetime | None
    taken: bool | None


class DoseResponse(BaseModel):
    taken: bool


class AdherenceDay(BaseModel):
    reminder_date: date
    doses_scheduled: int
    doses_taken: int
    doses_unanswered: int
    adherence_pct: Decimal


# ---------------- meals ----------------
class MealIn(BaseModel):
    meal_date: date
    meal_type: MealType
    description: str
    calories: int | None = Field(None, ge=0)
    is_planned: bool = True


class MealUpdate(BaseModel):
    meal_date: date | None = None
    meal_type: MealType | None = None
    description: str | None = None
    calories: int | None = Field(None, ge=0)
    is_planned: bool | None = None


class MealOut(ORM):
    meal_id: UUID
    patient_id: UUID
    meal_date: date
    meal_type: MealType
    description: str
    calories: int | None
    is_planned: bool
    diet_conflicts: list[str] = []


class MealDaySummary(BaseModel):
    meal_date: date
    planned_calories: int
    consumed_calories: int
    meals_planned: int
    meals_logged: int
    diet_conflicts: int


# ---------------- wellness ----------------
class WellnessIn(BaseModel):
    mood_score: int | None = Field(None, ge=1, le=10)
    sleep_hours: Decimal | None = Field(None, ge=0, le=24)
    water_intake_ml: int | None = Field(None, ge=0)


class WellnessOut(ORM):
    log_id: UUID
    patient_id: UUID
    log_date: date
    mood_score: int | None
    sleep_hours: Decimal | None
    water_intake_ml: int | None


class WellnessTrendRow(BaseModel):
    log_date: date
    mood_score: int | None
    sleep_hours: Decimal | None
    water_intake_ml: int | None
    mood_7d: Decimal | None
    sleep_7d: Decimal | None
    water_7d: Decimal | None
    mood_change_vs_prev_log: int | None
    days_logged_7d: int


class CorrelationOut(BaseModel):
    days_compared: int
    avg_adherence_pct: Decimal | None
    corr_adherence_mood: Decimal | None
    corr_adherence_sleep: Decimal | None
    avg_mood_full_adherence: Decimal | None
    avg_mood_partial_adherence: Decimal | None
    note: str = "Descriptive statistics only; not a clinical interpretation."


# ---------------- accounts ----------------
AccountRole = Literal["patient", "doctor"]


class LoginIn(BaseModel):
    email: str = Field(examples=["dr.someone@salusclinic.example"])
    password: str


class RegisterIn(PatientIn):
    password: str = Field(min_length=8, description="At least 8 characters")


class AccountOut(BaseModel):
    account_id: UUID
    email: str
    role: AccountRole
    patient_id: UUID | None
    doctor_id: UUID | None
    patient: PatientOut | None = None
    doctor: DoctorOut | None = None


class SessionOut(AccountOut):
    token: str = Field(description="Send as 'Authorization: Bearer <token>'")
    expires_at: datetime


class DemoAccount(BaseModel):
    email: str
    role: AccountRole
    name: str
    note: str


# ---------------- diary ----------------
class DiaryIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000, examples=["Fixed the leaky tap. Chai with Meena downstairs."])
    entry_date: date | None = Field(None, description="Defaults to today")


class DiaryUpdate(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class DiaryOut(ORM):
    entry_id: UUID
    patient_id: UUID
    entry_date: date
    body: str
    created_at: datetime
    updated_at: datetime


# ---------------- doctor profiles ----------------
class DoctorProfileIn(BaseModel):
    bio: str | None = Field(None, max_length=2000)
    qualifications: list[str] = Field([], examples=[["MBBS", "MD (Medicine)"]])
    practising_since: int | None = Field(None, ge=1950, le=2100, examples=[2009])
    languages: list[str] = Field([], examples=[["English", "Hindi", "Marathi"]])
    services: list[str] = []
    hospital: str | None = None
    registration_no: str | None = None

    @field_validator("qualifications", "languages", "services")
    @classmethod
    def _clean(cls, v: list[str]) -> list[str]:
        return [s.strip() for s in v if s and s.strip()]


class DoctorProfileOut(DoctorProfileIn):
    years_experience: int | None = None
    updated_at: datetime | None = None


DoctorDetail.model_rebuild()
