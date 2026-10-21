from datetime import date, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..auth import current_account, own_patient
from ..db import get_db
from ..models import DiaryEntry
from ..schemas import DiaryIn, DiaryOut, DiaryUpdate

router = APIRouter(tags=["Diary (login required)"])


@router.get("/patients/{patient_id}/diary", response_model=list[DiaryOut])
def list_entries(patient_id: UUID, start: date | None = Query(None, alias="from"),
                 end: date | None = Query(None, alias="to"), limit: int = Query(100, le=500),
                 _: dict = Depends(own_patient), db: Session = Depends(get_db)):
    """The patient's own diary, newest first (default: last 30 days)."""
    end = end or config.today()
    start = start or end - timedelta(days=29)
    return db.scalars(select(DiaryEntry)
                      .where(DiaryEntry.patient_id == patient_id, DiaryEntry.entry_date.between(start, end))
                      .order_by(DiaryEntry.entry_date.desc(), DiaryEntry.created_at.desc())
                      .limit(limit)).all()


@router.post("/patients/{patient_id}/diary", response_model=DiaryOut, status_code=201)
def add_entry(patient_id: UUID, body: DiaryIn, _: dict = Depends(own_patient), db: Session = Depends(get_db)):
    entry_date = body.entry_date or config.today()
    if entry_date > config.today():
        raise HTTPException(422, "Diary entries can’t be dated in the future")
    e = DiaryEntry(patient_id=patient_id, entry_date=entry_date, body=body.body.strip())
    db.add(e)
    db.commit()
    db.refresh(e)
    return e


def _own_entry(db: Session, entry_id: UUID, account: dict) -> DiaryEntry:
    e = db.get(DiaryEntry, entry_id)
    if not e or e.patient_id != account["patient_id"]:
        raise HTTPException(404, "Diary entry not found")
    return e


@router.patch("/diary/{entry_id}", response_model=DiaryOut)
def edit_entry(entry_id: UUID, body: DiaryUpdate, account: dict = Depends(current_account),
               db: Session = Depends(get_db)):
    e = _own_entry(db, entry_id, account)
    e.body = body.body.strip()
    db.commit()
    db.refresh(e)
    return e


@router.delete("/diary/{entry_id}", status_code=204)
def delete_entry(entry_id: UUID, account: dict = Depends(current_account), db: Session = Depends(get_db)):
    db.delete(_own_entry(db, entry_id, account))
    db.commit()
