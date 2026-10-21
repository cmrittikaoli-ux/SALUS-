"""Login sessions.

Passwords are bcrypt-hashed by pgcrypto's crypt(); a session token is 32
random bytes and only its SHA-256 is stored (auth_sessions). Routes that
touch private data depend on `own_patient` / `own_doctor`.
"""
from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .db import fetch_one, get_db

bearer = HTTPBearer(auto_error=False, description="Token from POST /auth/login")


def current_account(cred: HTTPAuthorizationCredentials | None = Depends(bearer),
                    db: Session = Depends(get_db)) -> dict:
    if not cred:
        raise HTTPException(401, "Log in first", headers={"WWW-Authenticate": "Bearer"})
    account = fetch_one(db, "SELECT * FROM fn_session_account(:t)", t=cred.credentials)
    if not account:
        raise HTTPException(401, "Your session has expired. Log in again.", headers={"WWW-Authenticate": "Bearer"})
    return account


def own_patient(patient_id: UUID, account: dict = Depends(current_account)) -> dict:
    if account["patient_id"] != patient_id:
        raise HTTPException(403, "You can only open your own records")
    return account


def own_doctor(doctor_id: UUID, account: dict = Depends(current_account)) -> dict:
    if account["doctor_id"] != doctor_id:
        raise HTTPException(403, "You can only edit your own profile")
    return account
