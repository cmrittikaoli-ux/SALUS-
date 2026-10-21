-- =====================================================================
-- SALUS: business logic that lives in the database
-- =====================================================================

DO $$
BEGIN
    EXECUTE format('ALTER DATABASE %I SET timezone = %L', current_database(), 'Asia/Kolkata');
END $$;
SET timezone = 'Asia/Kolkata';

-- ---------------------------------------------------------------------
-- 1. Appointment validation (trigger)
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_validate_appointment() RETURNS TRIGGER AS $$
DECLARE
    v_start  TIMESTAMPTZ := lower(NEW.slot);
    v_end    TIMESTAMPTZ := upper(NEW.slot);
    v_sched  doctor_schedules%ROWTYPE;
BEGIN
    IF NEW.status <> 'scheduled' THEN
        IF v_start > now() THEN
            RAISE EXCEPTION 'A future appointment can only be created as scheduled'
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END IF;

    IF v_start <= now() THEN
        RAISE EXCEPTION 'Cannot book a slot in the past (%)', v_start
            USING ERRCODE = 'check_violation';
    END IF;

    SELECT * INTO v_sched
      FROM doctor_schedules s
     WHERE s.doctor_id   = NEW.doctor_id
       AND s.day_of_week = EXTRACT(DOW FROM v_start)
       AND v_start::time >= s.start_time
       AND v_start::time <  s.end_time
     LIMIT 1;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Doctor does not work at % (outside weekly schedule)', v_start
            USING ERRCODE = 'check_violation';
    END IF;

    IF v_end - v_start <> make_interval(mins => v_sched.slot_minutes)
       OR (v_start::time + make_interval(mins => v_sched.slot_minutes)) > v_sched.end_time
       OR (EXTRACT(EPOCH FROM (v_start::time - v_sched.start_time))::int
           % (v_sched.slot_minutes * 60)) <> 0 THEN
        RAISE EXCEPTION 'Slot must be a % minute slot aligned to the schedule starting %',
                        v_sched.slot_minutes, v_sched.start_time
            USING ERRCODE = 'check_violation';
    END IF;

    IF EXISTS (SELECT 1 FROM doctor_unavailability u
                WHERE u.doctor_id = NEW.doctor_id
                  AND u.unavailable_range && NEW.slot) THEN
        RAISE EXCEPTION 'Doctor is unavailable (leave / blocked) at %', v_start
            USING ERRCODE = 'check_violation';
    END IF;

    IF EXISTS (SELECT 1 FROM appointments a
                WHERE a.patient_id = NEW.patient_id
                  AND a.appointment_id <> NEW.appointment_id
                  AND a.status = 'scheduled'
                  AND a.slot && NEW.slot) THEN
        RAISE EXCEPTION 'Patient already has another appointment at %', v_start
            USING ERRCODE = 'check_violation';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_validate_appointment
BEFORE INSERT ON appointments
FOR EACH ROW EXECUTE FUNCTION fn_validate_appointment();

CREATE OR REPLACE FUNCTION fn_validate_status_change() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.slot <> OLD.slot OR NEW.doctor_id <> OLD.doctor_id OR NEW.patient_id <> OLD.patient_id THEN
        RAISE EXCEPTION 'Appointments cannot be moved; cancel and book a new slot'
            USING ERRCODE = 'check_violation';
    END IF;

    IF NEW.status = OLD.status THEN
        RETURN NEW;
    END IF;

    IF OLD.status <> 'scheduled' THEN
        RAISE EXCEPTION 'Appointment is already % and cannot change', OLD.status
            USING ERRCODE = 'check_violation';
    END IF;

    IF NEW.status IN ('completed', 'no_show') AND lower(NEW.slot) > now() THEN
        RAISE EXCEPTION 'Cannot mark as % before the appointment has started', NEW.status
            USING ERRCODE = 'check_violation';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_validate_status_change
BEFORE UPDATE ON appointments
FOR EACH ROW EXECUTE FUNCTION fn_validate_status_change();

-- ---------------------------------------------------------------------
-- 2. Concurrency-safe booking
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_book_appointment(
    p_patient_id UUID,
    p_doctor_id  UUID,
    p_start      TIMESTAMPTZ
) RETURNS appointments AS $$
DECLARE
    v_minutes SMALLINT;
    v_row     appointments;
BEGIN
    PERFORM 1 FROM patients WHERE patient_id = p_patient_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Patient % not found', p_patient_id USING ERRCODE = 'no_data_found';
    END IF;

    PERFORM 1 FROM doctors WHERE doctor_id = p_doctor_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Doctor % not found', p_doctor_id USING ERRCODE = 'no_data_found';
    END IF;

    SELECT slot_minutes INTO v_minutes
      FROM doctor_schedules
     WHERE doctor_id = p_doctor_id
       AND day_of_week = EXTRACT(DOW FROM p_start)
       AND p_start::time >= start_time
       AND p_start::time <  end_time;

    IF v_minutes IS NULL THEN
        RAISE EXCEPTION 'Doctor does not work at % (outside weekly schedule)', p_start
            USING ERRCODE = 'check_violation';
    END IF;

    IF EXISTS (SELECT 1 FROM appointments
                WHERE doctor_id = p_doctor_id
                  AND status IN ('scheduled', 'completed')
                  AND slot && tstzrange(p_start, p_start + make_interval(mins => v_minutes))) THEN
        RAISE EXCEPTION 'Slot % is already booked', p_start USING ERRCODE = 'exclusion_violation';
    END IF;

    INSERT INTO appointments (patient_id, doctor_id, slot)
    VALUES (p_patient_id, p_doctor_id,
            tstzrange(p_start, p_start + make_interval(mins => v_minutes), '[)'))
    RETURNING * INTO v_row;

    RETURN v_row;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------
-- 3. Free slots for a doctor on a date
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_available_slots(p_doctor_id UUID, p_date DATE)
RETURNS TABLE (slot_start TIMESTAMPTZ, slot_end TIMESTAMPTZ) AS $$
    WITH day_blocks AS (
        SELECT gs::timestamptz AS s_start,
               (gs + make_interval(mins => ds.slot_minutes))::timestamptz AS s_end
          FROM doctor_schedules ds
          CROSS JOIN LATERAL generate_series(
                 p_date + ds.start_time,
                 p_date + ds.end_time - make_interval(mins => ds.slot_minutes),
                 make_interval(mins => ds.slot_minutes)) AS gs
         WHERE ds.doctor_id = p_doctor_id
           AND ds.day_of_week = EXTRACT(DOW FROM p_date)
    )
    SELECT b.s_start, b.s_end
      FROM day_blocks b
     WHERE b.s_start > now()
       AND NOT EXISTS (SELECT 1 FROM doctor_unavailability u
                        WHERE u.doctor_id = p_doctor_id
                          AND u.unavailable_range && tstzrange(b.s_start, b.s_end))
       AND NOT EXISTS (SELECT 1 FROM appointments a
                        WHERE a.doctor_id = p_doctor_id
                          AND a.status IN ('scheduled', 'completed')
                          AND a.slot && tstzrange(b.s_start, b.s_end))
     ORDER BY b.s_start;
$$ LANGUAGE sql STABLE;

-- ---------------------------------------------------------------------
-- 4. Multi-criteria doctor ranking
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_rank_doctors(
    p_lat            DOUBLE PRECISION,
    p_lon            DOUBLE PRECISION,
    p_specialty_id   SMALLINT DEFAULT NULL,
    p_max_budget     NUMERIC  DEFAULT 2000,
    p_radius_m       DOUBLE PRECISION DEFAULT 20000,
    p_min_rating     NUMERIC  DEFAULT 0,
    p_within_budget  BOOLEAN  DEFAULT FALSE,
    p_limit          INTEGER  DEFAULT 20,
    p_w_distance     NUMERIC  DEFAULT 0.4,
    p_w_fee          NUMERIC  DEFAULT 0.3,
    p_w_rating       NUMERIC  DEFAULT 0.3
) RETURNS TABLE (
    doctor_id         UUID,
    full_name         TEXT,
    specialty         TEXT,
    address_text      TEXT,
    consultation_fee  NUMERIC,
    average_rating    NUMERIC,
    rating_count      INTEGER,
    distance_km       NUMERIC,
    distance_score    NUMERIC,
    fee_score         NUMERIC,
    rating_score      NUMERIC,
    composite_score   NUMERIC
) AS $$
    WITH pt AS (
        SELECT ST_SetSRID(ST_MakePoint(p_lon, p_lat), 4326)::geography AS g
    ), scored AS (
        SELECT d.doctor_id, d.full_name, s.name AS specialty, d.address_text,
               d.consultation_fee, d.average_rating, d.rating_count,
               ST_Distance(d.location, pt.g) AS dist_m
          FROM doctors d
          JOIN specialties s ON s.specialty_id = d.specialty_id
          CROSS JOIN pt
         WHERE (p_specialty_id IS NULL OR d.specialty_id = p_specialty_id)
           AND ST_DWithin(d.location, pt.g, p_radius_m)
           AND d.average_rating >= p_min_rating
           AND (NOT p_within_budget OR d.consultation_fee <= p_max_budget)
    )
    SELECT doctor_id, full_name, specialty, address_text, consultation_fee,
           average_rating, rating_count,
           ROUND((dist_m / 1000)::numeric, 2),
           ROUND((1 - LEAST(dist_m / p_radius_m, 1))::numeric, 3),
           ROUND((1 - LEAST(consultation_fee / p_max_budget, 1))::numeric, 3),
           ROUND(average_rating / 5.0, 3),
           ROUND(( p_w_distance * (1 - LEAST(dist_m / p_radius_m, 1))
                 + p_w_fee      * (1 - LEAST(consultation_fee / p_max_budget, 1))
                 + p_w_rating   * (average_rating / 5.0))::numeric, 4) AS composite_score
      FROM scored
     ORDER BY composite_score DESC, dist_m
     LIMIT p_limit;
$$ LANGUAGE sql STABLE;

-- ---------------------------------------------------------------------
-- 5. Appointment reminders
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_schedule_appointment_reminders() RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' AND NEW.status = 'scheduled' THEN
        INSERT INTO reminders (appointment_id, remind_at)
        SELECT NEW.appointment_id, lower(NEW.slot) - o
          FROM unnest(ARRAY[interval '24 hours', interval '2 hours']) AS o
         WHERE lower(NEW.slot) - o > now()
        ON CONFLICT DO NOTHING;
    ELSIF TG_OP = 'UPDATE' AND NEW.status IN ('cancelled', 'no_show') AND OLD.status = 'scheduled' THEN
        DELETE FROM reminders WHERE appointment_id = NEW.appointment_id AND sent_at IS NULL;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_schedule_appointment_reminders
AFTER INSERT OR UPDATE OF status ON appointments
FOR EACH ROW EXECUTE FUNCTION fn_schedule_appointment_reminders();

CREATE OR REPLACE FUNCTION fn_dispatch_due_reminders() RETURNS INTEGER AS $$
DECLARE
    r   RECORD;
    n   INTEGER := 0;
BEGIN
    FOR r IN
        WITH due AS (
            SELECT rm.reminder_id
              FROM reminders rm
              JOIN appointments a ON a.appointment_id = rm.appointment_id
             WHERE rm.sent_at IS NULL
               AND rm.remind_at <= now()
               AND a.status = 'scheduled'
             FOR UPDATE OF rm SKIP LOCKED
        )
        UPDATE reminders rm
           SET sent_at = now()
          FROM due, appointments a, patients p, doctors d
         WHERE rm.reminder_id = due.reminder_id
           AND a.appointment_id = rm.appointment_id
           AND p.patient_id = a.patient_id
           AND d.doctor_id = a.doctor_id
        RETURNING rm.reminder_id, a.appointment_id, p.full_name AS patient, p.email,
                  d.full_name AS doctor, lower(a.slot) AS starts_at
    LOOP
        PERFORM pg_notify('salus_reminders', json_build_object(
            'kind', 'appointment', 'reminder_id', r.reminder_id,
            'appointment_id', r.appointment_id, 'patient', r.patient,
            'email', r.email, 'doctor', r.doctor, 'starts_at', r.starts_at)::text);
        n := n + 1;
    END LOOP;
    RETURN n;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------
-- 6. Medication dose reminders
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_generate_medication_reminder_log(p_date DATE DEFAULT CURRENT_DATE)
RETURNS INTEGER AS $$
DECLARE n INTEGER;
BEGIN
    INSERT INTO medication_reminder_log (medication_reminder_id, reminder_date)
    SELECT mr.medication_reminder_id, p_date
      FROM medication_reminders mr
      JOIN medications m ON m.medication_id = mr.medication_id
     WHERE m.active_range @> p_date
       AND EXTRACT(DOW FROM p_date)::smallint = ANY (mr.days_of_week)
    ON CONFLICT (medication_reminder_id, reminder_date) DO NOTHING;
    GET DIAGNOSTICS n = ROW_COUNT;
    RETURN n;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION fn_dispatch_due_medication_reminders() RETURNS INTEGER AS $$
DECLARE
    r RECORD;
    n INTEGER := 0;
BEGIN
    FOR r IN
        UPDATE medication_reminder_log l
           SET sent_at = now()
          FROM medication_reminders mr, medications m, patients p
         WHERE mr.medication_reminder_id = l.medication_reminder_id
           AND m.medication_id = mr.medication_id
           AND p.patient_id = m.patient_id
           AND l.sent_at IS NULL
           AND l.reminder_date = CURRENT_DATE
           AND mr.reminder_time <= LOCALTIME
        RETURNING l.log_id, p.full_name AS patient, p.email, m.drug_name, m.dosage,
                  mr.reminder_time, mr.label
    LOOP
        PERFORM pg_notify('salus_reminders', json_build_object(
            'kind', 'medication', 'log_id', r.log_id, 'patient', r.patient,
            'email', r.email, 'drug', r.drug_name, 'dosage', r.dosage,
            'time', r.reminder_time, 'label', r.label)::text);
        n := n + 1;
    END LOOP;
    RETURN n;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------
-- 7. Views for the medication tracker & analytics
-- ---------------------------------------------------------------------

CREATE OR REPLACE VIEW v_medication_overlaps AS
SELECT a.patient_id,
       a.medication_id  AS medication_a_id,
       a.drug_name      AS drug_a,
       b.medication_id  AS medication_b_id,
       b.drug_name      AS drug_b,
       a.active_range * b.active_range AS overlap_range,
       lower(a.active_range * b.active_range) AS overlap_start,
       upper(a.active_range * b.active_range) AS overlap_end
  FROM medications a
  JOIN medications b
    ON a.patient_id = b.patient_id
   AND a.medication_id < b.medication_id
   AND a.active_range && b.active_range;

CREATE OR REPLACE VIEW v_daily_adherence AS
SELECT m.patient_id,
       l.reminder_date,
       COUNT(*)                                   AS doses_scheduled,
       COUNT(*) FILTER (WHERE l.taken)            AS doses_taken,
       COUNT(*) FILTER (WHERE l.taken IS NULL)    AS doses_unanswered,
       ROUND(100.0 * COUNT(*) FILTER (WHERE l.taken) / COUNT(*), 1) AS adherence_pct
  FROM medication_reminder_log l
  JOIN medication_reminders mr ON mr.medication_reminder_id = l.medication_reminder_id
  JOIN medications m ON m.medication_id = mr.medication_id
 GROUP BY m.patient_id, l.reminder_date;

CREATE OR REPLACE VIEW v_doctor_stats AS
SELECT d.doctor_id, d.full_name, s.name AS specialty, d.consultation_fee,
       d.average_rating, d.rating_count,
       COUNT(a.*) FILTER (WHERE a.status = 'completed')  AS completed_appointments,
       COUNT(a.*) FILTER (WHERE a.status = 'scheduled')  AS upcoming_appointments,
       COUNT(a.*) FILTER (WHERE a.status = 'cancelled')  AS cancelled_appointments,
       COUNT(a.*) FILTER (WHERE a.status = 'no_show')    AS no_shows,
       RANK() OVER (PARTITION BY d.specialty_id ORDER BY d.average_rating DESC, d.rating_count DESC)
                                                         AS rank_in_specialty
  FROM doctors d
  JOIN specialties s ON s.specialty_id = d.specialty_id
  LEFT JOIN appointments a ON a.doctor_id = d.doctor_id
 GROUP BY d.doctor_id, s.name;

-- ---------------------------------------------------------------------
-- 8. Wellness trend (window functions)
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_wellness_trend(p_patient_id UUID, p_from DATE, p_to DATE)
RETURNS TABLE (
    log_date        DATE,
    mood_score      SMALLINT,
    sleep_hours     NUMERIC,
    water_intake_ml INTEGER,
    mood_7d         NUMERIC,
    sleep_7d        NUMERIC,
    water_7d        NUMERIC,
    mood_change_vs_prev_log SMALLINT,
    days_logged_7d  BIGINT
) AS $$
    SELECT * FROM (
        SELECT w.log_date, w.mood_score, w.sleep_hours, w.water_intake_ml,
               ROUND(AVG(w.mood_score)      OVER wk, 2),
               ROUND(AVG(w.sleep_hours)     OVER wk, 2),
               ROUND(AVG(w.water_intake_ml) OVER wk, 0),
               (w.mood_score - LAG(w.mood_score) OVER (ORDER BY w.log_date))::smallint,
               COUNT(*) OVER wk
          FROM wellness_logs w
         WHERE w.patient_id = p_patient_id
           AND w.log_date BETWEEN p_from - 6 AND p_to
        WINDOW wk AS (ORDER BY w.log_date RANGE BETWEEN INTERVAL '6 days' PRECEDING AND CURRENT ROW)
    ) t
    WHERE t.log_date >= p_from
    ORDER BY t.log_date
$$ LANGUAGE sql STABLE;

CREATE OR REPLACE FUNCTION fn_adherence_wellness_correlation(p_patient_id UUID, p_from DATE, p_to DATE)
RETURNS TABLE (
    days_compared      BIGINT,
    avg_adherence_pct  NUMERIC,
    corr_adherence_mood  NUMERIC,
    corr_adherence_sleep NUMERIC,
    avg_mood_full_adherence    NUMERIC,
    avg_mood_partial_adherence NUMERIC
) AS $$
    SELECT COUNT(*),
           ROUND(AVG(a.adherence_pct), 1),
           ROUND(corr(a.adherence_pct, w.mood_score)::numeric, 3),
           ROUND(corr(a.adherence_pct, w.sleep_hours)::numeric, 3),
           ROUND(AVG(w.mood_score) FILTER (WHERE a.adherence_pct = 100), 2),
           ROUND(AVG(w.mood_score) FILTER (WHERE a.adherence_pct < 100), 2)
      FROM v_daily_adherence a
      JOIN wellness_logs w
        ON w.patient_id = a.patient_id AND w.log_date = a.reminder_date
     WHERE a.patient_id = p_patient_id
       AND a.reminder_date BETWEEN p_from AND p_to
$$ LANGUAGE sql STABLE;
