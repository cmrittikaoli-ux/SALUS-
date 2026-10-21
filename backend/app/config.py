import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/salus")
TIMEZONE = os.getenv("SALUS_TIMEZONE", "Asia/Kolkata")

# The backend runs the reminder functions itself every minute when pg_cron
# is not installed. Set to "always" / "never" to override the auto-detect.
INTERNAL_SCHEDULER = os.getenv("SALUS_INTERNAL_SCHEDULER", "auto")
SCHEDULER_INTERVAL_SECONDS = int(os.getenv("SALUS_SCHEDULER_INTERVAL", "60"))


def today():
    """Today's date in the clinic's time zone (not the server's)."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo(TIMEZONE)).date()

# Show sample logins on the sign-in screen and let seed.py give every seeded
# patient and doctor this password. Turn off for anything but a demo.
DEMO_MODE = os.getenv("SALUS_DEMO_MODE", "true").lower() in ("1", "true", "yes")
DEMO_PASSWORD = os.getenv("SALUS_DEMO_PASSWORD", "salus123")
