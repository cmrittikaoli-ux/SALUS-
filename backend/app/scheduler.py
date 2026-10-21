"""Reminder plumbing on the backend side.

* Listener: LISTENs on the 'salus_reminders' channel. Whenever the DB
  dispatch functions mark a reminder as sent, they NOTIFY; this thread
  "delivers" it (here: log it and keep the last 200 in memory, which is
  where an email/SMS/push integration would plug in).
* Fallback scheduler: if pg_cron is not installed, run the same dispatch
  functions from the app every minute, so reminders still go out.
"""
from __future__ import annotations

import json
import logging
import threading
from collections import deque

import psycopg
from sqlalchemy import text

from . import config
from .db import engine

log = logging.getLogger("salus.reminders")
delivered: deque[dict] = deque(maxlen=200)
_stop = threading.Event()


def _raw_dsn() -> str:
    return config.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://")


def pg_cron_active() -> bool:
    with engine.connect() as c:
        has_ext = c.execute(text("SELECT 1 FROM pg_extension WHERE extname='pg_cron'")).first()
        if not has_ext:
            return False
        return bool(c.execute(text("SELECT count(*) FROM cron.job WHERE jobname LIKE 'salus_%' AND active")).scalar())


def run_dispatch_once() -> dict:
    """Same work the pg_cron jobs do; also exposed as POST /admin/dispatch."""
    with engine.begin() as c:
        generated = c.execute(text("SELECT fn_generate_medication_reminder_log(CURRENT_DATE)")).scalar()
        appt = c.execute(text("SELECT fn_dispatch_due_reminders()")).scalar()
        meds = c.execute(text("SELECT fn_dispatch_due_medication_reminders()")).scalar()
    return {"medication_log_rows_generated": generated, "appointment_reminders_sent": appt,
            "medication_reminders_sent": meds}


def _listener() -> None:
    while not _stop.is_set():
        try:
            with psycopg.connect(_raw_dsn(), autocommit=True) as conn:
                conn.execute("LISTEN salus_reminders")
                log.info("Listening for reminder notifications")
                while not _stop.is_set():
                    for n in conn.notifies(timeout=2.0):
                        payload = json.loads(n.payload)
                        delivered.append(payload)
                        log.info("REMINDER -> %s <%s>: %s", payload.get("patient"), payload.get("email"),
                                 payload.get("drug") or f"appointment with {payload.get('doctor')}")
        except Exception as exc:  # reconnect on DB restarts
            log.warning("reminder listener error: %s; retrying", exc)
            _stop.wait(5)


def _fallback_loop() -> None:
    while not _stop.wait(config.SCHEDULER_INTERVAL_SECONDS):
        try:
            result = run_dispatch_once()
            if any(result.values()):
                log.info("internal scheduler: %s", result)
        except Exception as exc:
            log.warning("internal scheduler error: %s", exc)


def start() -> dict:
    _stop.clear()
    threading.Thread(target=_listener, daemon=True, name="salus-listener").start()
    mode = config.INTERNAL_SCHEDULER
    use_internal = mode == "always" or (mode == "auto" and not pg_cron_active())
    if use_internal:
        threading.Thread(target=_fallback_loop, daemon=True, name="salus-scheduler").start()
    status = {"pg_cron": not use_internal, "internal_scheduler": use_internal}
    log.info("reminder scheduling: %s", status)
    return status


def stop() -> None:
    _stop.set()
