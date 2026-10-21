from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..db import fetch_all, fetch_one, get_db
from ..models import Patient, Specialty
from ..queries import APPOINTMENT_SELECT, get_patient
from ..schemas import AppointmentOut, AppointmentStatus, PatientIn, PatientOut, PatientUpdate, SpecialtyIn, SpecialtyOut

router = APIRouter(tags=["Patients & specialties"])


# ---------------- specialties ----------------
@router.get("/specialties", response_model=list[SpecialtyOut])
def list_specialties(db: Session = Depends(get_db)):
    return fetch_all(db, """SELECT s.specialty_id, s.name, count(d.doctor_id) AS doctor_count
                              FROM specialties s LEFT JOIN doctors d USING (specialty_id)
                             GROUP BY s.specialty_id ORDER BY s.name""")


@router.post("/specialties", response_model=SpecialtyOut, status_code=201)
def create_specialty(body: SpecialtyIn, db: Session = Depends(get_db)):
    s = Specialty(name=body.name)
    db.add(s)
    db.commit()
    return s


# ---------------- patients ----------------
@router.get("/patients", response_model=list[PatientOut])
def list_patients(search: str | None = Query(None, description="Name or email contains"),
                  limit: int = Query(50, le=500), offset: int = 0, db: Session = Depends(get_db)):
    q = select(Patient).order_by(Patient.full_name).limit(limit).offset(offset)
    if search:
        like = f"%{search}%"
        q = q.where(or_(Patient.full_name.ilike(like), Patient.email.ilike(like)))
    return db.scalars(q).all()


@router.post("/patients", response_model=PatientOut, status_code=201)
def create_patient(body: PatientIn, db: Session = Depends(get_db)):
    p = Patient(**body.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.get("/patients/{patient_id}", response_model=PatientOut)
def get_patient_by_id(patient_id: UUID, db: Session = Depends(get_db)):
    return get_patient(db, patient_id)


@router.patch("/patients/{patient_id}", response_model=PatientOut)
def update_patient(patient_id: UUID, body: PatientUpdate, db: Session = Depends(get_db)):
    p = get_patient(db, patient_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    db.commit()
    return p


@router.get("/patients/{patient_id}/appointments", response_model=list[AppointmentOut])
def patient_appointments(patient_id: UUID, status: AppointmentStatus | None = None,
                         upcoming: bool | None = Query(None, description="true = future only, false = past only"),
                         limit: int = Query(100, le=1000), db: Session = Depends(get_db)):
    get_patient(db, patient_id)
    sql = APPOINTMENT_SELECT + " WHERE a.patient_id = :pid"
    if status:
        sql += " AND a.status = CAST(:status AS appointment_status)"
    if upcoming is True:
        sql += " AND lower(a.slot) >= now()"
    elif upcoming is False:
        sql += " AND lower(a.slot) < now()"
    sql += " ORDER BY lower(a.slot) " + ("ASC" if upcoming else "DESC") + " LIMIT :limit"
    return fetch_all(db, sql, pid=patient_id, status=status, limit=limit)


@router.get("/patients/{patient_id}/dashboard")
def patient_dashboard(patient_id: UUID, db: Session = Depends(get_db)):
    """One-call summary across all modules for a patient's home screen."""
    p = get_patient(db, patient_id)
    return {
        "patient": PatientOut.model_validate(p),
        "next_appointment": fetch_one(db, APPOINTMENT_SELECT + """
             WHERE a.patient_id = :pid AND a.status = 'scheduled' AND lower(a.slot) >= now()
             ORDER BY lower(a.slot) LIMIT 1""", pid=patient_id),
        "upcoming_appointments": fetch_one(db, """SELECT count(*) AS n FROM appointments
             WHERE patient_id = :pid AND status = 'scheduled' AND lower(slot) >= now()""", pid=patient_id)["n"],
        "active_medications": fetch_all(db, """SELECT medication_id, drug_name, dosage FROM medications
             WHERE patient_id = :pid AND active_range @> CURRENT_DATE ORDER BY drug_name""", pid=patient_id),
        "overlapping_prescription_pairs_now": fetch_one(db, """SELECT count(*) AS n FROM v_medication_overlaps
             WHERE patient_id = :pid AND overlap_range @> CURRENT_DATE""", pid=patient_id)["n"],
        "doses_today": fetch_one(db, """
             SELECT count(*) AS scheduled, count(*) FILTER (WHERE l.taken) AS taken,
                    count(*) FILTER (WHERE l.sent_at IS NULL) AS not_yet_sent
               FROM medication_reminder_log l
               JOIN medication_reminders mr USING (medication_reminder_id)
               JOIN medications m USING (medication_id)
              WHERE m.patient_id = :pid AND l.reminder_date = CURRENT_DATE""", pid=patient_id),
        "wellness_last_7_days": fetch_one(db, """
             SELECT count(*) AS days_logged, round(avg(mood_score), 2) AS avg_mood,
                    round(avg(sleep_hours), 2) AS avg_sleep, round(avg(water_intake_ml)) AS avg_water_ml
               FROM wellness_logs WHERE patient_id = :pid AND log_date > CURRENT_DATE - 7""", pid=patient_id),
        "meals_today": fetch_all(db, """SELECT meal_type::text, description, calories, is_planned FROM meals
             WHERE patient_id = :pid AND meal_date = CURRENT_DATE ORDER BY meal_type""", pid=patient_id),
    }
