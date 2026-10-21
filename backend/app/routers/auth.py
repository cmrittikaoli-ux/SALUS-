from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import text
from sqlalchemy.orm import Session

from .. import config
from ..auth import bearer, current_account
from ..db import fetch_all, fetch_one, get_db
from ..queries import DOCTOR_SELECT, get_patient
from ..schemas import AccountOut, DemoAccount, LoginIn, PatientOut, RegisterIn, SessionOut

router = APIRouter(prefix="/auth", tags=["Accounts & login"])


def _with_owner(db: Session, account: dict) -> dict:
    """Attach the patient or doctor record the account belongs to."""
    if account["patient_id"]:
        account["patient"] = PatientOut.model_validate(get_patient(db, account["patient_id"]))
    if account["doctor_id"]:
        account["doctor"] = fetch_one(db, DOCTOR_SELECT + " WHERE d.doctor_id = :id", id=account["doctor_id"])
    return account


def _login(db: Session, email: str, password: str) -> dict:
    row = fetch_one(db, "SELECT * FROM fn_login(:e, :p)", e=email, p=password)
    db.commit()
    if not row:
        raise HTTPException(401, "That email and password don’t match an account")
    row["email"] = fetch_one(db, "SELECT email FROM accounts WHERE account_id = :id", id=row["account_id"])["email"]
    return _with_owner(db, row)


@router.post("/login", response_model=SessionOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    """Check the password (pgcrypto crypt) and open a 7-day session."""
    return _login(db, body.email, body.password)


@router.post("/register", response_model=SessionOut, status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    """Create a patient and their login in one transaction, then log in."""
    fetch_one(db, """
        WITH p AS (
            INSERT INTO patients (full_name, email, phone, date_of_birth, dietary_notes)
            VALUES (:name, :email, :phone, :dob, :diet)
            RETURNING patient_id)
        INSERT INTO accounts (email, password_hash, role, patient_id)
        SELECT :email, crypt(:pw, gen_salt('bf')), 'patient', patient_id FROM p
        RETURNING account_id""", name=body.full_name, email=body.email, phone=body.phone,
              dob=body.date_of_birth, diet=body.dietary_notes, pw=body.password)
    db.commit()
    return _login(db, body.email, body.password)


@router.get("/me", response_model=AccountOut)
def me(account: dict = Depends(current_account), db: Session = Depends(get_db)):
    return _with_owner(db, account)


@router.post("/logout", status_code=204)
def logout(cred: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)):
    if cred:
        db.execute(text("DELETE FROM auth_sessions WHERE token_hash = digest(:t, 'sha256')"), {"t": cred.credentials})
        db.commit()


@router.get("/demo-accounts", response_model=list[DemoAccount])
def demo_accounts(db: Session = Depends(get_db)):
    """A few seeded logins for the sign-in screen. Empty unless SALUS_DEMO_MODE is on."""
    if not config.DEMO_MODE:
        return []
    return fetch_all(db, """
        (SELECT a.email, 'patient' AS role, p.full_name AS name,
                coalesce(p.dietary_notes, 'Patient') AS note
           FROM accounts a JOIN patients p USING (patient_id)
          ORDER BY (p.full_name = 'Rashmi Shinde') DESC, p.full_name
          LIMIT 2)
        UNION ALL
        (SELECT a.email, 'doctor', 'Dr ' || d.full_name, s.name
           FROM accounts a JOIN doctors d USING (doctor_id) JOIN specialties s USING (specialty_id)
          ORDER BY d.average_rating DESC
          LIMIT 2)""")
