from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from .. import config
from ..auth import own_doctor
from ..db import fetch_all, fetch_one, get_db
from ..queries import APPOINTMENT_SELECT, DOCTOR_SELECT, require_doctor
from ..schemas import (AppointmentOut, AppointmentStatus, DoctorDetail, DoctorIn, DoctorOut, DoctorProfileIn,
                       DoctorProfileOut, RankedDoctor, ReviewOut, ScheduleBlock, Slot, UnavailabilityIn,
                       UnavailabilityOut)

router = APIRouter(prefix="/doctors", tags=["Doctors: search, schedule, availability"])


def _resolve_specialty(db: Session, specialty_id: int | None, specialty: str | None) -> int | None:
    if specialty_id is not None or not specialty:
        return specialty_id
    row = fetch_one(db, "SELECT specialty_id FROM specialties WHERE name ILIKE :n", n=specialty)
    if not row:
        raise HTTPException(404, f"Unknown specialty '{specialty}'. See GET /specialties")
    return row["specialty_id"]


@router.get("/search", response_model=list[RankedDoctor])
def search_doctors(
    lat: float = Query(..., ge=-90, le=90, description="Patient latitude", examples=[19.0178]),
    lon: float = Query(..., ge=-180, le=180, description="Patient longitude", examples=[72.8478]),
    specialty_id: int | None = None,
    specialty: str | None = Query(None, description="Specialty name, e.g. Cardiologist (alternative to specialty_id)"),
    max_budget: Decimal = Query(Decimal(2000), gt=0, description="Fee at/above this scores 0 on affordability"),
    radius_km: float = Query(20, gt=0, le=200),
    min_rating: Decimal = Query(Decimal(0), ge=0, le=5),
    within_budget: bool = Query(False, description="Hide doctors whose fee exceeds max_budget"),
    w_distance: float = Query(0.4, ge=0), w_fee: float = Query(0.3, ge=0), w_rating: float = Query(0.3, ge=0),
    include_next_available: bool = Query(True, description="Also compute each doctor's next free slot (7 days)"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Multi-criteria ranking: composite of proximity, affordability and rating (weights are normalised)."""
    total = w_distance + w_fee + w_rating
    if total == 0:
        raise HTTPException(422, "At least one weight must be > 0")
    rows = fetch_all(db, """
        SELECT * FROM fn_rank_doctors(
            CAST(:lat AS float8), CAST(:lon AS float8), CAST(:sid AS smallint), CAST(:budget AS numeric),
            CAST(:radius AS float8), CAST(:min_rating AS numeric), CAST(:within AS boolean), CAST(:limit AS integer),
            CAST(:wd AS numeric), CAST(:wf AS numeric), CAST(:wr AS numeric))""",
                     lat=lat, lon=lon, sid=_resolve_specialty(db, specialty_id, specialty), budget=max_budget,
                     radius=radius_km * 1000, min_rating=min_rating, within=within_budget, limit=limit,
                     wd=w_distance / total, wf=w_fee / total, wr=w_rating / total)
    if include_next_available and rows:
        nxt = fetch_all(db, """
            SELECT d.id AS doctor_id,
                   (SELECT min(s.slot_start)
                      FROM generate_series(CURRENT_DATE, CURRENT_DATE + 7, interval '1 day') g(day)
                      CROSS JOIN LATERAL fn_available_slots(d.id, g.day::date) s) AS next_available
              FROM unnest(CAST(:ids AS uuid[])) AS d(id)""", ids=[r["doctor_id"] for r in rows])
        by_id = {r["doctor_id"]: r["next_available"] for r in nxt}
        for r in rows:
            r["next_available"] = by_id.get(r["doctor_id"])
    return rows


@router.get("", response_model=list[DoctorOut])
def list_doctors(specialty_id: int | None = None, search: str | None = None,
                 limit: int = Query(100, le=500), offset: int = 0, db: Session = Depends(get_db)):
    sql = DOCTOR_SELECT + " WHERE (CAST(:sid AS smallint) IS NULL OR d.specialty_id = :sid)"
    if search:
        sql += " AND d.full_name ILIKE :like"
    sql += " ORDER BY d.average_rating DESC, d.full_name LIMIT :limit OFFSET :offset"
    return fetch_all(db, sql, sid=specialty_id, like=f"%{search}%", limit=limit, offset=offset)


@router.post("", response_model=DoctorDetail, status_code=201)
def create_doctor(body: DoctorIn, db: Session = Depends(get_db)):
    row = fetch_one(db, """
        INSERT INTO doctors (full_name, email, phone, specialty_id, consultation_fee, location, address_text)
        VALUES (:name, :email, :phone, :sid, :fee, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :addr)
        RETURNING doctor_id""", name=body.full_name, email=body.email, phone=body.phone, sid=body.specialty_id,
                    fee=body.consultation_fee, lon=body.longitude, lat=body.latitude, addr=body.address_text)
    _insert_blocks(db, row["doctor_id"], body.schedule)
    db.commit()
    return get_doctor(row["doctor_id"], db)


def _insert_blocks(db: Session, doctor_id: UUID, blocks: list[ScheduleBlock]) -> None:
    for b in blocks:
        db.execute(text("""INSERT INTO doctor_schedules (doctor_id, day_of_week, start_time, end_time, slot_minutes)
                           VALUES (:d, :dow, :s, :e, :m)"""),
                   dict(d=doctor_id, dow=b.day_of_week, s=b.start_time, e=b.end_time, m=b.slot_minutes))


def _schedule(db: Session, doctor_id: UUID) -> list[dict]:
    return fetch_all(db, """SELECT day_of_week, start_time, end_time, slot_minutes FROM doctor_schedules
                             WHERE doctor_id = :id ORDER BY day_of_week, start_time""", id=doctor_id)


@router.get("/{doctor_id}", response_model=DoctorDetail)
def get_doctor(doctor_id: UUID, db: Session = Depends(get_db)):
    row = fetch_one(db, DOCTOR_SELECT + " WHERE d.doctor_id = :id", id=doctor_id)
    if not row:
        raise HTTPException(404, f"Doctor {doctor_id} not found")
    row["schedule"] = _schedule(db, doctor_id)
    row["profile"] = _profile(db, doctor_id)
    return row


def _profile(db: Session, doctor_id: UUID) -> dict | None:
    return fetch_one(db, """SELECT bio, qualifications, practising_since, languages, services, hospital,
                                   registration_no, updated_at,
                                   EXTRACT(YEAR FROM CURRENT_DATE)::int - practising_since AS years_experience
                              FROM doctor_profiles WHERE doctor_id = :id""", id=doctor_id)


@router.get("/{doctor_id}/profile", response_model=DoctorProfileOut | None)
def get_profile(doctor_id: UUID, db: Session = Depends(get_db)):
    """Public profile: bio, qualifications, experience, languages, services. null if not filled in yet."""
    require_doctor(db, doctor_id)
    return _profile(db, doctor_id)


@router.put("/{doctor_id}/profile", response_model=DoctorProfileOut)
def save_profile(doctor_id: UUID, body: DoctorProfileIn, _: dict = Depends(own_doctor),
                 db: Session = Depends(get_db)):
    """Create or replace the profile. Login required, as this doctor."""
    if body.practising_since and body.practising_since > config.today().year:
        raise HTTPException(422, "Practising since can’t be in the future")
    db.execute(text("""
        INSERT INTO doctor_profiles (doctor_id, bio, qualifications, practising_since, languages, services,
                                     hospital, registration_no)
        VALUES (:id, :bio, :q, :since, :lang, :svc, :hosp, :reg)
        ON CONFLICT (doctor_id) DO UPDATE
           SET bio = EXCLUDED.bio, qualifications = EXCLUDED.qualifications,
               practising_since = EXCLUDED.practising_since, languages = EXCLUDED.languages,
               services = EXCLUDED.services, hospital = EXCLUDED.hospital,
               registration_no = EXCLUDED.registration_no"""),
               dict(id=doctor_id, bio=body.bio, q=body.qualifications, since=body.practising_since,
                    lang=body.languages, svc=body.services, hosp=body.hospital, reg=body.registration_no))
    db.commit()
    return _profile(db, doctor_id)


@router.get("/{doctor_id}/schedule", response_model=list[ScheduleBlock])
def get_schedule(doctor_id: UUID, db: Session = Depends(get_db)):
    require_doctor(db, doctor_id)
    return _schedule(db, doctor_id)


@router.put("/{doctor_id}/schedule", response_model=list[ScheduleBlock])
def replace_schedule(doctor_id: UUID, blocks: list[ScheduleBlock], db: Session = Depends(get_db)):
    """Replace the weekly schedule. Overlapping blocks are rejected by the EXCLUDE constraint.
    Existing bookings are kept even if they now fall outside the new hours."""
    require_doctor(db, doctor_id)
    db.execute(text("DELETE FROM doctor_schedules WHERE doctor_id = :id"), {"id": doctor_id})
    _insert_blocks(db, doctor_id, blocks)
    db.commit()
    return _schedule(db, doctor_id)


@router.get("/{doctor_id}/unavailability", response_model=list[UnavailabilityOut])
def list_unavailability(doctor_id: UUID, include_past: bool = False, db: Session = Depends(get_db)):
    require_doctor(db, doctor_id)
    return fetch_all(db, """SELECT unavailability_id, lower(unavailable_range) AS start_at,
                                   upper(unavailable_range) AS end_at, reason
                              FROM doctor_unavailability
                             WHERE doctor_id = :id AND (:past OR upper(unavailable_range) > now())
                             ORDER BY lower(unavailable_range)""", id=doctor_id, past=include_past)


@router.post("/{doctor_id}/unavailability", response_model=UnavailabilityOut, status_code=201)
def add_unavailability(doctor_id: UUID, body: UnavailabilityIn, db: Session = Depends(get_db)):
    """Block time (leave, conference). 409 if it overlaps existing leave.
    `affected_appointments` counts bookings already inside the window (they are not auto-cancelled)."""
    require_doctor(db, doctor_id)
    row = fetch_one(db, """INSERT INTO doctor_unavailability (doctor_id, unavailable_range, reason)
                           VALUES (:id, tstzrange(:s, :e, '[)'), :r)
                           RETURNING unavailability_id, lower(unavailable_range) AS start_at,
                                     upper(unavailable_range) AS end_at, reason""",
                    id=doctor_id, s=body.start_at, e=body.end_at, r=body.reason)
    row["affected_appointments"] = fetch_one(db, """SELECT count(*) AS n FROM appointments
        WHERE doctor_id = :id AND status = 'scheduled' AND slot && tstzrange(:s, :e, '[)')""",
                                             id=doctor_id, s=body.start_at, e=body.end_at)["n"]
    db.commit()
    return row


@router.delete("/{doctor_id}/unavailability/{unavailability_id}", status_code=204)
def delete_unavailability(doctor_id: UUID, unavailability_id: UUID, db: Session = Depends(get_db)):
    res = db.execute(text("DELETE FROM doctor_unavailability WHERE doctor_id = :d AND unavailability_id = :u"),
                     {"d": doctor_id, "u": unavailability_id})
    if res.rowcount == 0:
        raise HTTPException(404, "Unavailability entry not found")
    db.commit()


@router.get("/{doctor_id}/slots", response_model=dict[date, list[Slot]])
def available_slots(doctor_id: UUID, start_date: date | None = Query(None, alias="date"),
                    days: int = Query(1, ge=1, le=31), db: Session = Depends(get_db)):
    """Free, bookable slots = weekly schedule − leave − existing bookings − past times."""
    require_doctor(db, doctor_id)
    start_date = start_date or config.today()
    out: dict[date, list] = {}
    for i in range(days):
        d = start_date + timedelta(days=i)
        out[d] = fetch_all(db, "SELECT * FROM fn_available_slots(:id, :d)", id=doctor_id, d=d)
    return out


@router.get("/{doctor_id}/reviews", response_model=list[ReviewOut])
def doctor_reviews(doctor_id: UUID, limit: int = Query(50, le=500), offset: int = 0,
                   db: Session = Depends(get_db)):
    require_doctor(db, doctor_id)
    return fetch_all(db, """SELECT r.*, p.full_name AS patient_name FROM reviews r
                              JOIN patients p USING (patient_id)
                             WHERE r.doctor_id = :id ORDER BY r.created_at DESC LIMIT :l OFFSET :o""",
                     id=doctor_id, l=limit, o=offset)


@router.get("/{doctor_id}/appointments", response_model=list[AppointmentOut])
def doctor_appointments(doctor_id: UUID, on: date | None = Query(None, description="Only this date"),
                        status: AppointmentStatus | None = None, limit: int = Query(200, le=2000),
                        db: Session = Depends(get_db)):
    require_doctor(db, doctor_id)
    sql = APPOINTMENT_SELECT + " WHERE a.doctor_id = :id"
    if on:
        sql += " AND a.slot && tstzrange(CAST(:on AS date)::timestamptz, (CAST(:on AS date) + 1)::timestamptz)"
    if status:
        sql += " AND a.status = CAST(:status AS appointment_status)"
    sql += " ORDER BY lower(a.slot) DESC LIMIT :limit"
    return fetch_all(db, sql, id=doctor_id, on=on, status=status, limit=limit)
