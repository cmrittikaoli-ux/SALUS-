"""SALUS API — unified health platform for appointments and medication.

Run:  uvicorn app.main:app --reload     (from the backend/ folder)
Docs: http://localhost:8000/docs
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from . import errors, scheduler
from .db import engine
from .routers import admin, appointments, auth, diary, doctors, meals, medications, patients, wellness

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.scheduling = scheduler.start()
    yield
    scheduler.stop()


app = FastAPI(
    title="SALUS API",
    version="1.0.0",
    description=(
        "Unified health platform for appointments and medication. Doctor search & multi-criteria ranking, "
        "concurrency-safe booking, verified reviews, automated reminders, medication tracking with overlap "
        "detection, meal planning and a descriptive wellness tracker.\n\n"
        "Business rules are enforced in PostgreSQL (EXCLUDE constraints, triggers); the API maps DB errors "
        "to 409 / 422 responses."
    ),
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
errors.install(app)

for r in (auth.router, patients.router, doctors.router, appointments.router, medications.router, meals.router,
          wellness.router, diary.router, admin.router):
    app.include_router(r)


@app.get("/health", tags=["Reminders & admin"])
def health():
    with engine.connect() as c:
        db_time = c.execute(text("SELECT now()")).scalar()
    return {"status": "ok", "db_time": db_time, "scheduling": getattr(app.state, "scheduling", None)}
