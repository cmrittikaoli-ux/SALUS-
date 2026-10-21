-- =====================================================================
-- SALUS: Unified Health Platform for Appointments and Medication
-- Database schema (PostgreSQL 15+ / PostGIS)
-- =====================================================================

-- ---------------------------------------------------------------------
-- 0. Extensions
-- ---------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------
-- 1. Enumerated types
-- ---------------------------------------------------------------------
CREATE TYPE appointment_status AS ENUM ('scheduled', 'completed', 'cancelled', 'no_show');
CREATE TYPE meal_type          AS ENUM ('breakfast', 'lunch', 'dinner', 'snack');

-- ---------------------------------------------------------------------
-- 2. Core identity tables
-- ---------------------------------------------------------------------

CREATE TABLE patients (
    patient_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name       TEXT NOT NULL,
    email           TEXT NOT NULL UNIQUE,
    phone           TEXT,
    date_of_birth   DATE,
    dietary_notes   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE specialties (
    specialty_id    SMALLSERIAL PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE
);

CREATE TABLE doctors (
    doctor_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name           TEXT NOT NULL,
    email               TEXT NOT NULL UNIQUE,
    phone               TEXT,
    specialty_id        SMALLINT NOT NULL REFERENCES specialties(specialty_id),
    consultation_fee    NUMERIC(10,2) NOT NULL CHECK (consultation_fee >= 0),
    location            GEOGRAPHY(POINT, 4326) NOT NULL,
    address_text        TEXT,
    average_rating      NUMERIC(3,2) NOT NULL DEFAULT 0 CHECK (average_rating BETWEEN 0 AND 5),
    rating_count        INTEGER NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- 2b. Doctor schedule & availability
-- ---------------------------------------------------------------------

CREATE TABLE doctor_schedules (
    schedule_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doctor_id       UUID NOT NULL REFERENCES doctors(doctor_id) ON DELETE CASCADE,
    day_of_week     SMALLINT NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
    start_time      TIME NOT NULL,
    end_time        TIME NOT NULL,
    slot_minutes    SMALLINT NOT NULL DEFAULT 30 CHECK (slot_minutes > 0),

    CONSTRAINT valid_block CHECK (start_time < end_time),

    CONSTRAINT no_overlapping_blocks EXCLUDE USING gist (
        doctor_id WITH =,
        day_of_week WITH =,
        tsrange('2000-01-01'::date + start_time, '2000-01-01'::date + end_time) WITH &&
    )
);

CREATE INDEX idx_doctor_schedules_doctor ON doctor_schedules (doctor_id, day_of_week);

CREATE TABLE doctor_unavailability (
    unavailability_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doctor_id           UUID NOT NULL REFERENCES doctors(doctor_id) ON DELETE CASCADE,
    unavailable_range   TSTZRANGE NOT NULL,
    reason               TEXT,

    CONSTRAINT unavailable_range_not_empty CHECK (NOT isempty(unavailable_range)),

    CONSTRAINT no_overlapping_leave EXCLUDE USING gist (
        doctor_id WITH =,
        unavailable_range WITH &&
    )
);

CREATE INDEX idx_doctor_unavailability_doctor ON doctor_unavailability (doctor_id, unavailable_range);

-- ---------------------------------------------------------------------
-- 3. Appointment booking (concurrency-safe)
-- ---------------------------------------------------------------------

CREATE TABLE appointments (
    appointment_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id      UUID NOT NULL REFERENCES patients(patient_id),
    doctor_id       UUID NOT NULL REFERENCES doctors(doctor_id),
    slot            TSTZRANGE NOT NULL,
    status          appointment_status NOT NULL DEFAULT 'scheduled',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT slot_not_empty CHECK (NOT isempty(slot)),

    CONSTRAINT no_double_booking EXCLUDE USING gist (
        doctor_id WITH =,
        slot WITH &&
    ) WHERE (status IN ('scheduled', 'completed'))
);

CREATE INDEX idx_appointments_patient ON appointments (patient_id);
CREATE INDEX idx_appointments_doctor_time ON appointments (doctor_id, slot);

-- ---------------------------------------------------------------------
-- 4. Reviews & ratings (DB-enforced: only after a completed appointment)
-- ---------------------------------------------------------------------

CREATE TABLE reviews (
    review_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    appointment_id  UUID NOT NULL UNIQUE REFERENCES appointments(appointment_id),
    patient_id      UUID NOT NULL REFERENCES patients(patient_id),
    doctor_id       UUID NOT NULL REFERENCES doctors(doctor_id),
    rating          SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment         TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION fn_validate_review() RETURNS TRIGGER AS $$
DECLARE
    v_status appointment_status;
    v_patient UUID;
    v_doctor  UUID;
BEGIN
    SELECT status, patient_id, doctor_id
      INTO v_status, v_patient, v_doctor
      FROM appointments
     WHERE appointment_id = NEW.appointment_id
     FOR SHARE;

    IF v_status IS DISTINCT FROM 'completed' THEN
        RAISE EXCEPTION 'Review rejected: appointment % is not completed', NEW.appointment_id;
    END IF;

    IF v_patient IS DISTINCT FROM NEW.patient_id OR v_doctor IS DISTINCT FROM NEW.doctor_id THEN
        RAISE EXCEPTION 'Review rejected: patient/doctor do not match the appointment';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_validate_review
BEFORE INSERT ON reviews
FOR EACH ROW EXECUTE FUNCTION fn_validate_review();

CREATE OR REPLACE FUNCTION fn_refresh_doctor_rating() RETURNS TRIGGER AS $$
BEGIN
    UPDATE doctors d
       SET rating_count   = sub.cnt,
           average_rating = sub.avg_rating
      FROM (
            SELECT doctor_id, COUNT(*) AS cnt, ROUND(AVG(rating)::numeric, 2) AS avg_rating
              FROM reviews
             WHERE doctor_id = NEW.doctor_id
             GROUP BY doctor_id
           ) sub
     WHERE d.doctor_id = sub.doctor_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_refresh_doctor_rating
AFTER INSERT ON reviews
FOR EACH ROW EXECUTE FUNCTION fn_refresh_doctor_rating();

-- ---------------------------------------------------------------------
-- 5. Reminders (dispatched by pg_cron against appointments)
-- ---------------------------------------------------------------------

CREATE TABLE reminders (
    reminder_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    appointment_id  UUID NOT NULL REFERENCES appointments(appointment_id) ON DELETE CASCADE,
    remind_at       TIMESTAMPTZ NOT NULL,
    sent_at         TIMESTAMPTZ,
    UNIQUE (appointment_id, remind_at)
);

CREATE INDEX idx_reminders_pending ON reminders (remind_at) WHERE sent_at IS NULL;

-- ---------------------------------------------------------------------
-- 6. Medication tracker (interval-overlap detection)
-- ---------------------------------------------------------------------

CREATE TABLE medications (
    medication_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id      UUID NOT NULL REFERENCES patients(patient_id),
    drug_name       TEXT NOT NULL,
    dosage          TEXT NOT NULL,
    active_range    DATERANGE NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT active_range_not_empty CHECK (NOT isempty(active_range))
);

CREATE INDEX idx_medications_patient_range ON medications USING gist (patient_id, active_range);

CREATE TABLE medication_reminders (
    medication_reminder_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    medication_id            UUID NOT NULL REFERENCES medications(medication_id) ON DELETE CASCADE,
    reminder_time             TIME NOT NULL,
    days_of_week              SMALLINT[] NOT NULL DEFAULT '{0,1,2,3,4,5,6}',
    label                     TEXT,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT valid_days_of_week CHECK (
        days_of_week <@ ARRAY[0,1,2,3,4,5,6]::SMALLINT[] AND cardinality(days_of_week) > 0
    ),
    UNIQUE (medication_id, reminder_time)
);

CREATE INDEX idx_medication_reminders_medication ON medication_reminders (medication_id);

CREATE TABLE medication_reminder_log (
    log_id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    medication_reminder_id    UUID NOT NULL REFERENCES medication_reminders(medication_reminder_id) ON DELETE CASCADE,
    reminder_date              DATE NOT NULL,
    sent_at                    TIMESTAMPTZ,
    taken                       BOOLEAN,

    UNIQUE (medication_reminder_id, reminder_date)
);

CREATE INDEX idx_medication_reminder_log_pending ON medication_reminder_log (reminder_date) WHERE sent_at IS NULL;

-- ---------------------------------------------------------------------
-- 7. Meal plan
-- ---------------------------------------------------------------------

CREATE TABLE meals (
    meal_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id      UUID NOT NULL REFERENCES patients(patient_id),
    meal_date       DATE NOT NULL,
    meal_type       meal_type NOT NULL,
    description     TEXT NOT NULL,
    calories        INTEGER CHECK (calories >= 0),
    is_planned      BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_meals_patient_date ON meals (patient_id, meal_date);

-- ---------------------------------------------------------------------
-- 8. Combined wellness tracker (mood / sleep / water — descriptive only)
-- ---------------------------------------------------------------------

CREATE TABLE wellness_logs (
    log_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id      UUID NOT NULL REFERENCES patients(patient_id),
    log_date        DATE NOT NULL,
    mood_score      SMALLINT CHECK (mood_score BETWEEN 1 AND 10),
    sleep_hours     NUMERIC(3,1) CHECK (sleep_hours BETWEEN 0 AND 24),
    water_intake_ml INTEGER CHECK (water_intake_ml >= 0),
    UNIQUE (patient_id, log_date)
);

CREATE INDEX idx_wellness_patient_date ON wellness_logs (patient_id, log_date);

-- ---------------------------------------------------------------------
-- 9. Indexing strategy for search & ranking
-- ---------------------------------------------------------------------

CREATE INDEX idx_doctors_location ON doctors USING gist (location);

CREATE INDEX idx_doctors_specialty_rating ON doctors (specialty_id, average_rating DESC);
