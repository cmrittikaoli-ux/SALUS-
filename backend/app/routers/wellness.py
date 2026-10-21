from datetime import date, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..db import fetch_all, fetch_one, get_db
from ..models import WellnessLog
from ..queries import get_patient
from ..schemas import CorrelationOut, WellnessIn, WellnessOut, WellnessTrendRow

router = APIRouter(prefix="/patients/{patient_id}/wellness", tags=["Wellness tracker"])


def _range(start, end, default_days=30):
    end = end or config.today()
    return start or end - timedelta(days=default_days - 1), end


@router.put("/{log_date}", response_model=WellnessOut)
def upsert_log(patient_id: UUID, log_date: date, body: WellnessIn, db: Session = Depends(get_db)):
    """Create or update the single daily log (mood 1–10, sleep hours, water ml)."""
    get_patient(db, patient_id)
    if log_date > config.today():
        raise HTTPException(422, "Cannot log wellness for a future date")
    log = db.scalar(select(WellnessLog).where(WellnessLog.patient_id == patient_id, WellnessLog.log_date == log_date))
    if not log:
        log = WellnessLog(patient_id=patient_id, log_date=log_date)
        db.add(log)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(log, k, v)
    db.commit()
    db.refresh(log)
    return log


@router.get("", response_model=list[WellnessOut])
def list_logs(patient_id: UUID, start: date | None = Query(None, alias="from"), end: date | None = Query(None, alias="to"),
              db: Session = Depends(get_db)):
    get_patient(db, patient_id)
    start, end = _range(start, end)
    return db.scalars(select(WellnessLog).where(WellnessLog.patient_id == patient_id,
                                                WellnessLog.log_date.between(start, end))
                      .order_by(WellnessLog.log_date)).all()


@router.delete("/{log_date}", status_code=204)
def delete_log(patient_id: UUID, log_date: date, db: Session = Depends(get_db)):
    log = db.scalar(select(WellnessLog).where(WellnessLog.patient_id == patient_id, WellnessLog.log_date == log_date))
    if not log:
        raise HTTPException(404, "No log for that date")
    db.delete(log)
    db.commit()


@router.get("/trend", response_model=list[WellnessTrendRow])
def trend(patient_id: UUID, start: date | None = Query(None, alias="from"), end: date | None = Query(None, alias="to"),
          db: Session = Depends(get_db)):
    """Rolling 7-day averages (window function, calendar-week RANGE frame) + day-over-day mood change."""
    get_patient(db, patient_id)
    start, end = _range(start, end)
    return fetch_all(db, "SELECT * FROM fn_wellness_trend(:pid, :s, :e)", pid=patient_id, s=start, e=end)


@router.get("/weekly")
def weekly_summary(patient_id: UUID, weeks: int = Query(8, ge=1, le=52), db: Session = Depends(get_db)):
    """Week-by-week averages with change vs the previous week (LAG)."""
    get_patient(db, patient_id)
    return fetch_all(db, """
        WITH w AS (
            SELECT date_trunc('week', log_date)::date AS week_start,
                   count(*) AS days_logged,
                   round(avg(mood_score), 2) AS avg_mood,
                   round(avg(sleep_hours), 2) AS avg_sleep,
                   round(avg(water_intake_ml)) AS avg_water_ml
              FROM wellness_logs
             WHERE patient_id = :pid AND log_date >= date_trunc('week', CURRENT_DATE) - make_interval(weeks => :w - 1)
             GROUP BY 1)
        SELECT *, avg_mood  - LAG(avg_mood)  OVER (ORDER BY week_start) AS mood_change,
                  avg_sleep - LAG(avg_sleep) OVER (ORDER BY week_start) AS sleep_change
          FROM w ORDER BY week_start""", pid=patient_id, w=weeks)


@router.get("/adherence-correlation", response_model=CorrelationOut)
def adherence_correlation(patient_id: UUID, start: date | None = Query(None, alias="from"),
                          end: date | None = Query(None, alias="to"), db: Session = Depends(get_db)):
    """Joins the daily medication-adherence view with the wellness log and reports Pearson r."""
    get_patient(db, patient_id)
    start, end = _range(start, end)
    return fetch_one(db, "SELECT * FROM fn_adherence_wellness_correlation(:pid, :s, :e)", pid=patient_id, s=start, e=end)
