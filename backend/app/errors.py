"""Translate PostgreSQL errors raised by constraints and triggers into clean
HTTP responses, so the database stays the source of truth for the rules."""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError

# SQLSTATE -> (HTTP status, error code)
SQLSTATE_MAP = {
    "23P01": (409, "slot_conflict"),        # EXCLUDE constraint (double booking / overlapping leave or blocks)
    "23505": (409, "duplicate"),            # UNIQUE
    "23503": (422, "invalid_reference"),    # FK
    "23514": (422, "rule_violation"),       # CHECK + our trigger rules
    "23502": (422, "missing_value"),        # NOT NULL
    "P0001": (422, "rule_violation"),       # RAISE EXCEPTION without errcode (review trigger)
    "02000": (404, "not_found"),            # no_data_found raised by fn_book_appointment
    "22007": (400, "invalid_value"),
    "22008": (400, "invalid_value"),
    "22P02": (400, "invalid_value"),
    "22000": (400, "invalid_value"),
}

FRIENDLY = {
    "no_double_booking": "That slot was just taken by another booking. Please choose another slot.",
    "no_overlapping_leave": "This leave overlaps an existing unavailability entry for the doctor.",
    "no_overlapping_blocks": "This schedule block overlaps another block on the same day.",
    "patients_email_key": "A patient with this email already exists.",
    "accounts_email_key": "An account with this email already exists. Try logging in.",
    "doctors_email_key": "A doctor with this email already exists.",
    "reviews_appointment_id_key": "This appointment has already been reviewed.",
    "specialties_name_key": "That specialty already exists.",
    "wellness_logs_patient_id_log_date_key": "A wellness log for this date already exists.",
    "medication_reminders_medication_id_reminder_time_key": "This medication already has a reminder at that time.",
}


def install(app: FastAPI) -> None:
    @app.exception_handler(DBAPIError)
    async def db_error(_: Request, exc: DBAPIError):
        orig = getattr(exc, "orig", None)
        sqlstate = getattr(orig, "sqlstate", None)
        diag = getattr(orig, "diag", None)
        constraint = getattr(diag, "constraint_name", None) if diag else None
        message = getattr(diag, "message_primary", None) if diag else None
        status, code = SQLSTATE_MAP.get(sqlstate, (500, "database_error"))
        detail = FRIENDLY.get(constraint) or message or "Database error"
        body = {"error": code, "detail": detail}
        if constraint:
            body["constraint"] = constraint
        return JSONResponse(status_code=status, content=body)
