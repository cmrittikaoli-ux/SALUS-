from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import fetch_all, fetch_one, get_db
from ..queries import APPOINTMENT_SELECT, get_appointment
from ..schemas import AppointmentIn, AppointmentOut, AppointmentStatus, ReminderOut, ReviewIn, ReviewOut

router = APIRouter(tags=["Appointments & reviews"])


@router.post("/appointments", response_model=AppointmentOut, status_code=201,
             responses={409: {"description": "Slot already booked (concurrency-safe)"},
                        422: {"description": "Outside schedule, on leave, in the past, or patient busy"}})
def book_appointment(body: AppointmentIn, db: Session = Depends(get_db)):
    """Books through `fn_book_appointment`: locks the doctor row (FOR UPDATE), validates against the
    weekly schedule and leave, and inserts. The EXCLUDE constraint is the final guarantee against
    double booking. Reminders (24h / 2h before) are created by trigger."""
    row = fetch_one(db, "SELECT appointment_id FROM fn_book_appointment(:p, :d, :s)",
                    p=body.patient_id, d=body.doctor_id, s=body.start_at)
    db.commit()
    return get_appointment(db, row["appointment_id"])


@router.get("/appointments", response_model=list[AppointmentOut])
def list_appointments(patient_id: UUID | None = None, doctor_id: UUID | None = None,
                      status: AppointmentStatus | None = None,
                      start: datetime | None = Query(None, alias="from"), end: datetime | None = Query(None, alias="to"),
                      limit: int = Query(100, le=1000), offset: int = 0, db: Session = Depends(get_db)):
    where, params = [], {"limit": limit, "offset": offset}
    if patient_id:
        where.append("a.patient_id = :pid"); params["pid"] = patient_id
    if doctor_id:
        where.append("a.doctor_id = :did"); params["did"] = doctor_id
    if status:
        where.append("a.status = CAST(:status AS appointment_status)"); params["status"] = status
    if start:
        where.append("lower(a.slot) >= :start"); params["start"] = start
    if end:
        where.append("lower(a.slot) < :end"); params["end"] = end
    sql = APPOINTMENT_SELECT + (" WHERE " + " AND ".join(where) if where else "")
    sql += " ORDER BY lower(a.slot) DESC LIMIT :limit OFFSET :offset"
    return fetch_all(db, sql, **params)


@router.get("/appointments/{appointment_id}", response_model=AppointmentOut)
def appointment_detail(appointment_id: UUID, db: Session = Depends(get_db)):
    return get_appointment(db, appointment_id)


def _set_status(db: Session, appointment_id: UUID, status: str) -> dict:
    get_appointment(db, appointment_id)
    # Transition rules are enforced by trg_validate_status_change
    db.execute(text("UPDATE appointments SET status = CAST(:s AS appointment_status) WHERE appointment_id = :id"),
               {"s": status, "id": appointment_id})
    db.commit()
    return get_appointment(db, appointment_id)


@router.post("/appointments/{appointment_id}/cancel", response_model=AppointmentOut)
def cancel_appointment(appointment_id: UUID, db: Session = Depends(get_db)):
    """Frees the slot for rebooking (cancelled rows are outside the EXCLUDE constraint) and
    removes unsent reminders."""
    return _set_status(db, appointment_id, "cancelled")


@router.post("/appointments/{appointment_id}/complete", response_model=AppointmentOut)
def complete_appointment(appointment_id: UUID, db: Session = Depends(get_db)):
    return _set_status(db, appointment_id, "completed")


@router.post("/appointments/{appointment_id}/no-show", response_model=AppointmentOut)
def mark_no_show(appointment_id: UUID, db: Session = Depends(get_db)):
    return _set_status(db, appointment_id, "no_show")


@router.get("/appointments/{appointment_id}/reminders", response_model=list[ReminderOut])
def appointment_reminders(appointment_id: UUID, db: Session = Depends(get_db)):
    get_appointment(db, appointment_id)
    return fetch_all(db, "SELECT * FROM reminders WHERE appointment_id = :id ORDER BY remind_at", id=appointment_id)


# ---------------- reviews ----------------
@router.post("/reviews", response_model=ReviewOut, status_code=201,
             responses={422: {"description": "Appointment not completed, or patient mismatch (DB trigger)"},
                        409: {"description": "Appointment already reviewed"}})
def create_review(body: ReviewIn, db: Session = Depends(get_db)):
    """The *database* decides whether the review is allowed (trg_validate_review): the appointment must be
    completed and belong to this patient. The doctor's average rating updates by trigger."""
    appt = get_appointment(db, body.appointment_id)
    row = fetch_one(db, """INSERT INTO reviews (appointment_id, patient_id, doctor_id, rating, comment)
                           VALUES (:a, :p, :d, :r, :c) RETURNING *""",
                    a=body.appointment_id, p=body.patient_id, d=appt["doctor_id"], r=body.rating, c=body.comment)
    db.commit()
    return row


@router.get("/reviews/{review_id}", response_model=ReviewOut)
def get_review(review_id: UUID, db: Session = Depends(get_db)):
    row = fetch_one(db, """SELECT r.*, p.full_name AS patient_name FROM reviews r JOIN patients p USING (patient_id)
                            WHERE review_id = :id""", id=review_id)
    if not row:
        raise HTTPException(404, "Review not found")
    return row
