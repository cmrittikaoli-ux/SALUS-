from datetime import date, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.orm import Session, selectinload

from .. import config
from ..db import fetch_all, fetch_one, get_db
from ..models import Medication, MedicationReminder
from ..queries import get_patient
from ..schemas import (AdherenceDay, DoseOut, DoseResponse, MedicationCreated, MedicationIn, MedicationOut,
                       MedicationUpdate, MedReminderIn, MedReminderOut, OverlapOut)

router = APIRouter(tags=["Medication tracker"])

OVERLAP_SQL = """
SELECT medication_a_id, drug_a, medication_b_id, drug_b, overlap_start, overlap_end,
       (overlap_end - overlap_start) AS overlap_days
  FROM v_medication_overlaps
 WHERE patient_id = :pid"""


def _out(m: Medication) -> dict:
    today = config.today()
    lo, hi = m.active_range.lower, m.active_range.upper
    return dict(medication_id=m.medication_id, patient_id=m.patient_id, drug_name=m.drug_name, dosage=m.dosage,
                start_date=lo, end_date=hi, is_active_today=(lo is None or lo <= today) and (hi is None or today < hi),
                reminders=m.reminders, created_at=m.created_at)


def _get_med(db: Session, medication_id: UUID) -> Medication:
    m = db.scalar(select(Medication).options(selectinload(Medication.reminders))
                  .where(Medication.medication_id == medication_id))
    if not m:
        raise HTTPException(404, f"Medication {medication_id} not found")
    return m


@router.get("/patients/{patient_id}/medications", response_model=list[MedicationOut])
def list_medications(patient_id: UUID, active_on: date | None = Query(None, description="Only those active on this date"),
                     db: Session = Depends(get_db)):
    get_patient(db, patient_id)
    q = (select(Medication).options(selectinload(Medication.reminders))
         .where(Medication.patient_id == patient_id).order_by(Medication.created_at.desc()))
    if active_on:
        q = q.where(Medication.active_range.contains(active_on))
    return [_out(m) for m in db.scalars(q).all()]


@router.post("/patients/{patient_id}/medications", response_model=MedicationCreated, status_code=201)
def add_medication(patient_id: UUID, body: MedicationIn, db: Session = Depends(get_db)):
    """Adds a prescription (+ dose reminder times). Overlapping prescriptions are allowed but reported
    back in `overlaps` — a scheduling signal, not pharmacological advice."""
    get_patient(db, patient_id)
    m = Medication(patient_id=patient_id, drug_name=body.drug_name, dosage=body.dosage,
                   active_range=Range(body.start_date, body.end_date, bounds="[)"))
    m.reminders = [MedicationReminder(**r.model_dump()) for r in body.reminders]
    db.add(m)
    db.flush()
    overlaps = fetch_all(db, OVERLAP_SQL + " AND :mid IN (medication_a_id, medication_b_id)", pid=patient_id,
                         mid=m.medication_id)
    # If it starts today, make today's dose rows exist straight away
    db.execute(text("SELECT fn_generate_medication_reminder_log(CURRENT_DATE)"))
    db.commit()
    return {**_out(_get_med(db, m.medication_id)), "overlaps": overlaps}


@router.get("/medications/{medication_id}", response_model=MedicationOut)
def get_medication(medication_id: UUID, db: Session = Depends(get_db)):
    return _out(_get_med(db, medication_id))


@router.patch("/medications/{medication_id}", response_model=MedicationOut)
def update_medication(medication_id: UUID, body: MedicationUpdate, db: Session = Depends(get_db)):
    """Change dosage, stop a medication (set end_date) or make it ongoing again."""
    m = _get_med(db, medication_id)
    if body.dosage:
        m.dosage = body.dosage
    if body.end_date or body.make_ongoing:
        new_end = None if body.make_ongoing else body.end_date
        if new_end is not None and new_end <= m.active_range.lower:
            raise HTTPException(422, "end_date must be after start_date")
        m.active_range = Range(m.active_range.lower, new_end, bounds="[)")
    db.commit()
    return _out(_get_med(db, medication_id))


@router.delete("/medications/{medication_id}", status_code=204)
def delete_medication(medication_id: UUID, db: Session = Depends(get_db)):
    db.delete(_get_med(db, medication_id))
    db.commit()


@router.get("/patients/{patient_id}/medications/overlaps", response_model=list[OverlapOut])
def medication_overlaps(patient_id: UUID, active_on: date | None = Query(None, description="Only overlaps covering this date"),
                        db: Session = Depends(get_db)):
    """Interval-overlap detection with the range `&&` operator (GiST-indexed)."""
    get_patient(db, patient_id)
    sql = OVERLAP_SQL + (" AND overlap_range @> CAST(:d AS date)" if active_on else "")
    return fetch_all(db, sql + " ORDER BY overlap_start", pid=patient_id, d=active_on)


# ---------------- dose reminders ----------------
@router.post("/medications/{medication_id}/reminders", response_model=MedReminderOut, status_code=201)
def add_dose_reminder(medication_id: UUID, body: MedReminderIn, db: Session = Depends(get_db)):
    m = _get_med(db, medication_id)
    r = MedicationReminder(medication_id=m.medication_id, **body.model_dump())
    db.add(r)
    db.commit()
    return r


@router.delete("/medication-reminders/{medication_reminder_id}", status_code=204)
def delete_dose_reminder(medication_reminder_id: UUID, db: Session = Depends(get_db)):
    r = db.get(MedicationReminder, medication_reminder_id)
    if not r:
        raise HTTPException(404, "Reminder not found")
    db.delete(r)
    db.commit()


@router.get("/patients/{patient_id}/doses", response_model=list[DoseOut])
def doses_for_day(patient_id: UUID, on: date | None = Query(None, description="Defaults to today"),
                  db: Session = Depends(get_db)):
    """The day's dose schedule (from the recurrence rules) joined with what was sent / taken."""
    get_patient(db, patient_id)
    on = on or config.today()
    return fetch_all(db, """
        SELECT l.log_id, mr.medication_reminder_id, m.medication_id, m.drug_name, m.dosage,
               mr.reminder_time, mr.label, l.sent_at, l.taken
          FROM medications m
          JOIN medication_reminders mr ON mr.medication_id = m.medication_id
          LEFT JOIN medication_reminder_log l
                 ON l.medication_reminder_id = mr.medication_reminder_id AND l.reminder_date = :d
         WHERE m.patient_id = :pid
           AND m.active_range @> CAST(:d AS date)
           AND EXTRACT(DOW FROM CAST(:d AS date))::smallint = ANY (mr.days_of_week)
         ORDER BY mr.reminder_time, m.drug_name""", pid=patient_id, d=on)


@router.post("/medication-log/{log_id}", response_model=DoseOut)
def respond_to_dose(log_id: UUID, body: DoseResponse, db: Session = Depends(get_db)):
    """Patient confirms (taken=true) or skips (taken=false) a dose."""
    row = fetch_one(db, "UPDATE medication_reminder_log SET taken = :t WHERE log_id = :id RETURNING log_id",
                    t=body.taken, id=log_id)
    if not row:
        raise HTTPException(404, "Dose log entry not found")
    db.commit()
    return fetch_one(db, """
        SELECT l.log_id, mr.medication_reminder_id, m.medication_id, m.drug_name, m.dosage,
               mr.reminder_time, mr.label, l.sent_at, l.taken
          FROM medication_reminder_log l
          JOIN medication_reminders mr USING (medication_reminder_id)
          JOIN medications m USING (medication_id)
         WHERE l.log_id = :id""", id=log_id)


@router.get("/patients/{patient_id}/adherence", response_model=list[AdherenceDay])
def adherence(patient_id: UUID, start: date | None = Query(None, alias="from"), end: date | None = Query(None, alias="to"),
              db: Session = Depends(get_db)):
    get_patient(db, patient_id)
    end = end or config.today()
    start = start or end - timedelta(days=29)
    return fetch_all(db, """SELECT reminder_date, doses_scheduled, doses_taken, doses_unanswered, adherence_pct
                              FROM v_daily_adherence
                             WHERE patient_id = :pid AND reminder_date BETWEEN :s AND :e
                             ORDER BY reminder_date""", pid=patient_id, s=start, e=end)
