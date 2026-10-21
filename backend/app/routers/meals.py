from datetime import date, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..db import get_db
from ..diet_rules import check_meal
from ..models import Meal
from ..queries import get_patient
from ..schemas import MealDaySummary, MealIn, MealOut, MealUpdate

router = APIRouter(tags=["Meal plan"])


def _out(m: Meal, notes: str | None) -> dict:
    d = MealOut.model_validate(m).model_dump()
    d["diet_conflicts"] = check_meal(m.description, notes)
    return d


def _range(start, end):
    today = config.today()
    return (start or today - timedelta(days=6), end or today + timedelta(days=7))


@router.get("/patients/{patient_id}/meals", response_model=list[MealOut])
def list_meals(patient_id: UUID, start: date | None = Query(None, alias="from"), end: date | None = Query(None, alias="to"),
               planned: bool | None = Query(None, description="true = plan, false = logged/consumed"),
               db: Session = Depends(get_db)):
    """Meals in a date range, each cross-checked against the patient's dietary_notes."""
    p = get_patient(db, patient_id)
    start, end = _range(start, end)
    q = (select(Meal).where(Meal.patient_id == patient_id, Meal.meal_date.between(start, end))
         .order_by(Meal.meal_date, Meal.meal_type))
    if planned is not None:
        q = q.where(Meal.is_planned == planned)
    return [_out(m, p.dietary_notes) for m in db.scalars(q).all()]


@router.post("/patients/{patient_id}/meals", response_model=MealOut, status_code=201)
def add_meal(patient_id: UUID, body: MealIn, db: Session = Depends(get_db)):
    p = get_patient(db, patient_id)
    m = Meal(patient_id=patient_id, **body.model_dump())
    db.add(m)
    db.commit()
    db.refresh(m)
    return _out(m, p.dietary_notes)


@router.patch("/meals/{meal_id}", response_model=MealOut)
def update_meal(meal_id: UUID, body: MealUpdate, db: Session = Depends(get_db)):
    m = db.get(Meal, meal_id)
    if not m:
        raise HTTPException(404, "Meal not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(m, k, v)
    db.commit()
    return _out(m, get_patient(db, m.patient_id).dietary_notes)


@router.delete("/meals/{meal_id}", status_code=204)
def delete_meal(meal_id: UUID, db: Session = Depends(get_db)):
    m = db.get(Meal, meal_id)
    if not m:
        raise HTTPException(404, "Meal not found")
    db.delete(m)
    db.commit()


@router.get("/patients/{patient_id}/meals/summary", response_model=list[MealDaySummary])
def meal_summary(patient_id: UUID, start: date | None = Query(None, alias="from"), end: date | None = Query(None, alias="to"),
                 db: Session = Depends(get_db)):
    """Per-day planned vs consumed calories, and how many meals conflict with the dietary notes."""
    p = get_patient(db, patient_id)
    start, end = _range(start, end)
    meals = db.scalars(select(Meal).where(Meal.patient_id == patient_id, Meal.meal_date.between(start, end))).all()
    days: dict[date, dict] = {}
    for m in meals:
        d = days.setdefault(m.meal_date, dict(meal_date=m.meal_date, planned_calories=0, consumed_calories=0,
                                              meals_planned=0, meals_logged=0, diet_conflicts=0))
        if m.is_planned:
            d["planned_calories"] += m.calories or 0
            d["meals_planned"] += 1
        else:
            d["consumed_calories"] += m.calories or 0
            d["meals_logged"] += 1
        if check_meal(m.description, p.dietary_notes):
            d["diet_conflicts"] += 1
    return [days[k] for k in sorted(days)]
