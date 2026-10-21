# SALUS

A unified health platform for appointments and medication, built as a DBMS mini project by Mrittika Chakraborty, Eshna Kumar and Swara Nirgun.

This repository contains:

- the PostgreSQL + PostGIS database, with pg_cron jobs
- a FastAPI backend
- a React frontend
- a dummy-data generator (Mumbai-based) and a ready-made SQL dump
- the project report and ER diagrams (`docs/`)

The core schema is `db/01_schema.sql`: tables, constraints and triggers. Business logic is layered on top as functions, triggers and views in `db/02_functions.sql`, and `db/06_accounts_diary_profiles.sql` adds logins, the patient diary and doctor profiles. The SQL files keep only their section headings; the explanations are in this README.

```
salus/
├── db/
│   ├── 01_schema.sql          core schema: tables, constraints, triggers
│   ├── 02_functions.sql       booking, slots, ranking, reminder jobs, triggers, views
│   ├── 03_cron.sql            pg_cron job registrations
│   ├── 04_seed_data.sql       pure-SQL snapshot of the dummy data (generated 29 Sep 2026)
│   ├── 05_demo_queries.sql    one query per "Key Database Concept", for the viva/report
│   ├── 06_accounts_diary_profiles.sql   logins (pgcrypto), patient diary, doctor profiles
│   └── Dockerfile             postgis + pg_cron image
├── frontend/                  React app (Vite)
├── backend/app/               FastAPI app (routers/, models.py, schemas.py, scheduler.py …)
├── scripts/seed.py            dummy-data generator (dates relative to today)
├── scripts/setup_db.sh        create DB → apply SQL → seed
├── tests/test_api.py          18 end-to-end tests (incl. a 20-way booking race)
├── docs/                      report and ER diagrams
├── docker-compose.yml, Dockerfile, requirements.txt
```

## Quick start

### Option A — Docker (easiest, especially on Windows)
```bash
docker compose up --build
```
Open **http://localhost:8000/docs** (Swagger UI). Postgres is on `localhost:5432` (user/password `postgres`/`postgres`, database `salus`). The API seeds the database on first start.

### Option B — local PostgreSQL
Requirements: PostgreSQL 15+ with **PostGIS**. **pg_cron** is optional.

1. *(optional, for pg_cron)* Add these lines to `postgresql.conf`, then restart Postgres:
   ```
   shared_preload_libraries = 'pg_cron'
   cron.database_name = 'salus'
   cron.timezone = 'Asia/Kolkata'
   cron.use_background_workers = on     # otherwise jobs fail with "connection failed"
   max_worker_processes = 20
   ```
2. Set up the database and the backend:
   ```bash
   pip install -r requirements.txt
   PGUSER=postgres PGPASSWORD=postgres ./scripts/setup_db.sh
   cd backend && uvicorn app.main:app --reload
   ```
   Set `DATABASE_URL` if the database credentials differ (see `.env.example`).

**Windows without Docker:** pg_cron isn't packaged for Windows. Skip `03_cron.sql` and the backend will detect that and run the same reminder functions every minute itself (`SALUS_INTERNAL_SCHEDULER=auto`). The SQL files can also be run by hand with `psql -f`, followed by `python scripts/seed.py`.

**Loading the data without Python:** run `01`, `02` (and optionally `03`), then `06`, then `psql -d salus -f db/04_seed_data.sql`, then `psql -d salus -c "SELECT fn_create_demo_accounts('salus123')"` so everyone can log in (the snapshot has no profiles or diary entries). Its dates are frozen at 29 Sep 2026, so "upcoming" appointments will drift into the past. `seed.py` always generates data relative to today.

### Tests and demo
```bash
pytest -v tests/                                  # API must be running on :8000
psql -d salus -f db/05_demo_queries.sql           # the showcase SQL
```

## How each objective is implemented

| Objective | Where it's enforced | Notes |
|---|---|---|
| **Doctor search & ranking** | `fn_rank_doctors()` + `GET /doctors/search` | score = 0.4·proximity + 0.3·affordability + 0.3·rating. Weights are adjustable per request. Uses `ST_DWithin` on the GiST index, filters by specialty, budget and minimum rating, and returns each doctor's next free slot. |
| **Conflict-free booking** | `fn_book_appointment()` → `SELECT … FOR UPDATE` on the doctor row, then the `no_double_booking` EXCLUDE constraint as a hard backstop | Tested with 20 concurrent requests for one slot: exactly one gets `201`, nineteen get `409`. |
| Booking rules | `trg_validate_appointment` | The slot must be in the future, inside the weekly schedule, aligned to the slot grid, not during leave, and the patient must not already be booked at that time. Rejections return `422`. |
| Status lifecycle | `trg_validate_status_change` | `scheduled → completed / cancelled / no_show` only. A future appointment can't be marked completed. Cancelling frees the slot for rebooking. |
| **Verified reviews** | `trg_validate_review` + `trg_refresh_doctor_rating` | The API passes the insert straight to the DB. The trigger decides, and the error maps to `422`. |
| **Automated reminders** | `trg_schedule_appointment_reminders` creates rows 24h and 2h before. `fn_dispatch_due_reminders()` runs every minute via pg_cron. | The dispatcher marks rows sent (`SKIP LOCKED`) and sends `NOTIFY salus_reminders`. The API `LISTEN`s and logs each delivery; see `GET /admin/notifications`. Real email/SMS would hook in there. |
| **Medication tracker** | `v_medication_overlaps` (range `&&` and `*`), `fn_generate_medication_reminder_log()`, `fn_dispatch_due_medication_reminders()`, `v_daily_adherence` | Adding a prescription returns any overlapping ones as information only. Patients mark each dose taken or skipped. |
| **Meal plan** | `diet_rules.py` | Each meal is checked against the patient's `dietary_notes` (vegetarian, Jain, vegan, lactose, gluten, nut, low-sugar, low-sodium) and conflicts are flagged. |
| **Wellness tracker** | `fn_wellness_trend()` (7-day `RANGE` window, `LAG`), `/weekly`, `fn_adherence_wellness_correlation()` (`corr()`) | Descriptive only. The rolling window uses a calendar week, so days the patient skipped don't distort it. |
| **Login** | `accounts`, `auth_sessions`, `fn_login()`, `fn_session_account()` | Passwords are bcrypt hashes made by pgcrypto `crypt()`. A session token is 32 random bytes; only its SHA-256 is stored, and it expires after 7 days. |
| **Diary** | `diary_entries` + `/patients/{id}/diary` | Free-text notes for everyday things. Login required; a patient can only read or change their own entries (`403` otherwise). |
| **Doctor profiles** | `doctor_profiles` | Bio, qualifications, languages, services, hospital, registration. Experience is computed from `practising_since`, so it never goes stale. Only the doctor can edit it. |
| **Indexing** | GiST and composite indexes in `01_schema.sql` | `05_demo_queries.sql` §8 shows `EXPLAIN` using `idx_doctors_location`. |

Schedules are local wall-clock times. The DB time zone is set to `Asia/Kolkata`, and all timestamps come back with a `+05:30` offset.

## API overview (full interactive docs at `/docs`)

| Area | Endpoints |
|---|---|
| Patients | `GET/POST /patients`, `GET/PATCH /patients/{id}`, `GET /patients/{id}/appointments`, `GET /patients/{id}/dashboard` |
| Specialties | `GET/POST /specialties` |
| Doctors | `GET /doctors/search`, `GET/POST /doctors`, `GET /doctors/{id}`, `GET/PUT /doctors/{id}/schedule`, `GET/POST/DELETE /doctors/{id}/unavailability`, `GET /doctors/{id}/slots?date=&days=`, `GET /doctors/{id}/reviews`, `GET /doctors/{id}/appointments` |
| Appointments | `POST /appointments`, `GET /appointments`, `GET /appointments/{id}`, `POST /appointments/{id}/cancel`, `/complete`, `/no-show`, `GET /appointments/{id}/reminders` |
| Reviews | `POST /reviews`, `GET /reviews/{id}` |
| Medications | `GET/POST /patients/{id}/medications`, `GET/PATCH/DELETE /medications/{id}`, `GET /patients/{id}/medications/overlaps`, `POST /medications/{id}/reminders`, `DELETE /medication-reminders/{id}`, `GET /patients/{id}/doses?on=`, `POST /medication-log/{log_id}`, `GET /patients/{id}/adherence` |
| Meals | `GET/POST /patients/{id}/meals`, `PATCH/DELETE /meals/{id}`, `GET /patients/{id}/meals/summary` |
| Wellness | `PUT/DELETE /patients/{id}/wellness/{date}`, `GET /patients/{id}/wellness`, `/trend`, `/weekly`, `/adherence-correlation` |
| Login | `POST /auth/login`, `POST /auth/register` (new patient), `GET /auth/me`, `POST /auth/logout`, `GET /auth/demo-accounts` |
| Diary (login) | `GET/POST /patients/{id}/diary`, `PATCH/DELETE /diary/{entry_id}` |
| Doctor profile | `GET /doctors/{id}/profile` (also inside `GET /doctors/{id}`), `PUT /doctors/{id}/profile` (login as that doctor) |
| Admin | `GET /reminders/pending`, `POST /admin/dispatch`, `GET /admin/notifications`, `GET /admin/jobs`, `GET /admin/stats`, `GET /health` |

A medication's `end_date` is **exclusive** (the first day it's no longer taken), matching the `[start, end)` daterange in the schema. `null` means ongoing.

## Dummy data (seed 42)

| Table | Rows | What's in it |
|---|---|---|
| specialties | 15 | GP, Cardiologist, Dermatologist, Orthopedic, Pediatrician, … Dentist |
| doctors | 74 | Spread across 26 Mumbai neighbourhoods (Colaba → Thane/Vashi). Realistic INR fees per specialty and real coordinates. |
| doctor_schedules | 560 | Morning/evening clinics, Sundays mostly off, half-day Saturdays. Slot length varies by specialty (15–45 min). |
| doctor_unavailability | 32 | Leave, conferences and hospital-duty blocks, past and upcoming |
| patients | 300 | Ages 1–82. About 45% have dietary notes. |
| appointments | ~3,600 | 120 days of history (≈82% completed, 11% cancelled, 7% no-show) plus ~550 upcoming bookings over the next 14 days, **booked through `fn_book_appointment`** |
| reviews | ~1,670 | Each doctor has a hidden "quality", so ratings differ meaningfully between doctors. Every review goes through the review trigger. |
| reminders | ~6,400 | Past ones marked sent. Upcoming ones are created by the trigger. |
| medications / reminders / dose log | ~450 / ~590 / ~9,800 | 20 common drugs, chronic and short courses, weekly and Mon/Wed/Fri schedules, 30 days of dose history. Each patient has their own adherence level. |
| meals | ~11,700 | 14 days logged plus 7 days planned, Indian meals that mostly respect dietary notes (a few deliberate slips) |
| doctor_profiles / diary_entries / accounts | 74 / ~750 / 374 | A profile for every doctor, a few weeks of mundane diary notes for ~60% of patients, and a login for every patient and doctor (password `salus123`) |
| wellness_logs | ~10,600 | 60 days, with realistic gaps and weekend effects, mildly linked to adherence so the correlation demo shows a result |

Re-generate any time with `python scripts/seed.py --reset` (options: `--seed`, `--patients`, `--history-days`, `--future-days`).

All emails use `example.com` / `salusclinic.example`, and all people are fictional.

## Not included (out of scope for the DB project)
- Full access control. Login is required for the diary and for editing a doctor profile, but the older endpoints (appointments, medicines, meals, wellness, the admin routes) still accept any caller, so the demo pages and tests keep working. Put `own_patient` / `own_doctor` from `backend/app/auth.py` on those routes before any real use, and turn off `SALUS_DEMO_MODE`.
- Real notification delivery. Reminders are marked sent and logged via LISTEN/NOTIFY; plug an email or SMS provider into `scheduler._listener`.

## Frontend

A React app (Vite) in `frontend/`, built for the demo. It talks to the API above.

```bash
cd frontend
npm install
npm run dev            # opens on http://localhost:5173 (API must be running on :8000)
```
Point it at a different API with `VITE_API_URL` (see `frontend/.env.example`). The fonts are bundled, and the map is drawn in SVG, so it works offline.

**Log in** with any seeded email and the password `salus123`; the sign-in screen lists a few to click. *New patient* creates an account. The screens shown depend on who logs in:

| View | Screens |
|---|---|
| Patient | Home (next visit, today's doses, 7-day wellness, meals), Find a doctor (ranked list + Mumbai map with distance rings, live weight sliders), Doctor page (14-day slot picker, booking, reviews), Appointments (cancel, review completed visits, reminder status), Medicines (dose strip, overlap timeline, adherence calendar, add prescription), Meals (week grid with diet-clash flags), Wellness (rolling 7-day charts, weekly table, adherence vs mood, diary). Home and Wellness both have the private diary. Each doctor page has an About section. |
| Doctor | Day list (mark seen / no-show / cancel), Weekly hours editor, Leave, Reviews, My profile (edit, with a preview of what patients see) |
| Under the hood | 20-request booking race, eight "try to break the rules" checks, live reminder feed, pg_cron job status |

Every screen has a **Show the SQL** button (bottom of the left rail) that opens the query, function or constraint behind it.

**Demo tip:** log in as *Nikhil Bhosale* (`nikhil.bhosale@example.com`): lactose intolerant, with upcoming visits, reviewable visits, overlapping prescriptions and diary entries, so every screen has data. To show a diet clash, add "Aloo paratha with curd" as a meal he ate.
