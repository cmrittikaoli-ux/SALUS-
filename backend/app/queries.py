"""Shared SQL fragments and lookups."""
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .db import fetch_one
from .models import Patient

APPOINTMENT_SELECT = """
SELECT a.appointment_id, a.patient_id, p.full_name AS patient_name,
       a.doctor_id, d.full_name AS doctor_name, s.name AS specialty,
       lower(a.slot) AS start_at, upper(a.slot) AS end_at,
       a.status::text AS status, a.created_at,
       EXISTS (SELECT 1 FROM reviews r WHERE r.appointment_id = a.appointment_id) AS has_review
  FROM appointments a
  JOIN patients p    ON p.patient_id = a.patient_id
  JOIN doctors d     ON d.doctor_id = a.doctor_id
  JOIN specialties s ON s.specialty_id = d.specialty_id
"""

DOCTOR_SELECT = """
SELECT d.doctor_id, d.full_name, d.email, d.phone, d.specialty_id, s.name AS specialty,
       d.consultation_fee, ST_Y(d.location::geometry) AS latitude, ST_X(d.location::geometry) AS longitude,
       d.address_text, d.average_rating, d.rating_count, d.created_at
  FROM doctors d
  JOIN specialties s ON s.specialty_id = d.specialty_id
"""


def get_patient(db: Session, patient_id: UUID) -> Patient:
    p = db.get(Patient, patient_id)
    if not p:
        raise HTTPException(404, f"Patient {patient_id} not found")
    return p


def get_appointment(db: Session, appointment_id: UUID) -> dict:
    row = fetch_one(db, APPOINTMENT_SELECT + " WHERE a.appointment_id = :id", id=appointment_id)
    if not row:
        raise HTTPException(404, f"Appointment {appointment_id} not found")
    return row


def require_doctor(db: Session, doctor_id: UUID) -> None:
    if not fetch_one(db, "SELECT 1 AS ok FROM doctors WHERE doctor_id = :id", id=doctor_id):
        raise HTTPException(404, f"Doctor {doctor_id} not found")
