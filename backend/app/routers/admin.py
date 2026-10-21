from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import scheduler
from ..db import fetch_all, fetch_one, get_db
from ..schemas import ReminderOut

router = APIRouter(tags=["Reminders & admin"])


@router.get("/reminders/pending", response_model=list[ReminderOut])
def pending_reminders(within_hours: int = Query(48, ge=1, le=720), db: Session = Depends(get_db)):
    """Appointment reminders not yet sent, due within the next N hours."""
    return fetch_all(db, """
        SELECT r.*, p.full_name AS patient_name, d.full_name AS doctor_name, lower(a.slot) AS appointment_start
          FROM reminders r
          JOIN appointments a USING (appointment_id)
          JOIN patients p ON p.patient_id = a.patient_id
          JOIN doctors d ON d.doctor_id = a.doctor_id
         WHERE r.sent_at IS NULL AND r.remind_at <= now() + make_interval(hours => :h)
         ORDER BY r.remind_at""", h=within_hours)


@router.post("/admin/dispatch")
def dispatch_now():
    """Run the reminder jobs immediately (the same functions pg_cron calls every minute)."""
    return scheduler.run_dispatch_once()


@router.get("/admin/notifications")
def delivered_notifications(limit: int = Query(50, le=200)):
    """Reminders this API process received via LISTEN/NOTIFY (newest first) — where email/SMS would hook in."""
    return list(reversed(scheduler.delivered))[:limit]


@router.get("/admin/jobs")
def cron_jobs(db: Session = Depends(get_db)):
    """pg_cron jobs and their latest runs (empty if pg_cron isn't installed)."""
    if not fetch_one(db, "SELECT 1 AS ok FROM pg_extension WHERE extname = 'pg_cron'"):
        return {"pg_cron": False, "jobs": [], "recent_runs": []}
    return {
        "pg_cron": True,
        "jobs": fetch_all(db, "SELECT jobid, jobname, schedule, command, active FROM cron.job ORDER BY jobid"),
        "recent_runs": fetch_all(db, """SELECT jobid, status, return_message, start_time, end_time
                                          FROM cron.job_run_details ORDER BY start_time DESC LIMIT 20"""),
    }


@router.get("/admin/stats")
def stats(db: Session = Depends(get_db)):
    """Row counts and a few headline numbers across all modules."""
    counts = fetch_one(db, """SELECT
        (SELECT count(*) FROM patients) AS patients,
        (SELECT count(*) FROM doctors) AS doctors,
        (SELECT count(*) FROM appointments) AS appointments,
        (SELECT count(*) FROM appointments WHERE status = 'scheduled' AND lower(slot) > now()) AS upcoming_appointments,
        (SELECT count(*) FROM reviews) AS reviews,
        (SELECT count(*) FROM reminders WHERE sent_at IS NULL) AS reminders_pending,
        (SELECT count(*) FROM medications WHERE active_range @> CURRENT_DATE) AS active_medications,
        (SELECT count(*) FROM v_medication_overlaps WHERE overlap_range @> CURRENT_DATE) AS overlapping_pairs_today,
        (SELECT count(*) FROM meals) AS meals,
        (SELECT count(*) FROM wellness_logs) AS wellness_logs""")
    counts["appointments_by_status"] = {r["status"]: r["n"] for r in fetch_all(
        db, "SELECT status::text, count(*) AS n FROM appointments GROUP BY 1")}
    counts["top_doctors_by_specialty"] = fetch_all(db, """
        SELECT specialty, full_name, average_rating, rating_count, completed_appointments
          FROM v_doctor_stats WHERE rank_in_specialty = 1 ORDER BY specialty""")
    return counts
