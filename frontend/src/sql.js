// The SQL behind each screen, shown in the drawer during the demo.
// Kept in sync by hand with db/02_functions.sql.

export const SQL = {
  home: {
    title: 'Patient home',
    intro: 'One API call (/patients/{id}/dashboard) runs these reads across every module.',
    blocks: [
      ['Next appointment', `SELECT ... FROM appointments a
  JOIN doctors d USING (doctor_id)
 WHERE a.patient_id = :pid
   AND a.status = 'scheduled'
   AND lower(a.slot) >= now()
 ORDER BY lower(a.slot)
 LIMIT 1;`],
      ['Prescriptions overlapping today', `SELECT count(*) FROM v_medication_overlaps
 WHERE patient_id = :pid
   AND overlap_range @> CURRENT_DATE;`],
      ['Today’s doses', `SELECT count(*) AS scheduled,
       count(*) FILTER (WHERE l.taken) AS taken
  FROM medication_reminder_log l
  JOIN medication_reminders mr USING (medication_reminder_id)
  JOIN medications m USING (medication_id)
 WHERE m.patient_id = :pid
   AND l.reminder_date = CURRENT_DATE;`],
      ['Login: fn_login(email, password)', `SELECT * INTO v FROM accounts
 WHERE lower(email) = lower(:email);
IF v.password_hash <> crypt(:password, v.password_hash)
THEN RETURN;  -- no row = wrong email or password
INSERT INTO auth_sessions (token_hash, account_id)
VALUES (digest(:token, 'sha256'), v.account_id);`],
    ],
  },
  find: {
    title: 'Doctor search and ranking',
    intro: 'Multi-criteria ranking in one function. ST_DWithin uses the GiST index idx_doctors_location.',
    blocks: [
      ['fn_rank_doctors(lat, lon, specialty, budget, radius, ...)', `WITH pt AS (
  SELECT ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography AS g
)
SELECT d.full_name, d.consultation_fee, d.average_rating,
       ST_Distance(d.location, pt.g) / 1000 AS distance_km,
       ( :w_dist   * (1 - LEAST(ST_Distance(d.location, pt.g) / :radius, 1))
       + :w_fee    * (1 - LEAST(d.consultation_fee / :budget, 1))
       + :w_rating * (d.average_rating / 5.0) ) AS composite_score
  FROM doctors d, pt
 WHERE d.specialty_id = :specialty
   AND ST_DWithin(d.location, pt.g, :radius)
 ORDER BY composite_score DESC
 LIMIT 20;`],
      ['Next free slot per doctor', `SELECT min(s.slot_start)
  FROM generate_series(CURRENT_DATE, CURRENT_DATE + 7, '1 day') g(day)
  CROSS JOIN LATERAL fn_available_slots(:doctor_id, g.day::date) s;`],
    ],
  },
  doctor: {
    title: 'Slots and booking',
    intro: 'Free slots are generated from the weekly schedule. Booking is concurrency-safe at two levels.',
    blocks: [
      ['fn_available_slots(doctor, date)', `-- weekly schedule, cut into slots
SELECT gs AS slot_start
  FROM doctor_schedules ds,
       generate_series(:date + ds.start_time,
                       :date + ds.end_time - slot_len, slot_len) gs
 WHERE ds.doctor_id = :doctor AND ds.day_of_week = EXTRACT(DOW FROM :date)
-- minus leave
   AND NOT EXISTS (SELECT 1 FROM doctor_unavailability u
                    WHERE u.unavailable_range && tstzrange(gs, gs + slot_len))
-- minus existing bookings
   AND NOT EXISTS (SELECT 1 FROM appointments a
                    WHERE a.status IN ('scheduled','completed')
                      AND a.slot && tstzrange(gs, gs + slot_len));`],
      ['fn_book_appointment(patient, doctor, start)', `-- 1. serialise bookings for this doctor (row lock)
SELECT 1 FROM doctors WHERE doctor_id = :doctor FOR UPDATE;
-- 2. insert; trg_validate_appointment checks schedule, leave, past
INSERT INTO appointments (patient_id, doctor_id, slot)
VALUES (:patient, :doctor, tstzrange(:start, :start + slot_len));`],
      ['The hard guarantee (schema)', `CONSTRAINT no_double_booking EXCLUDE USING gist (
    doctor_id WITH =,
    slot      WITH &&
) WHERE (status IN ('scheduled', 'completed'))`],
      ['Profile: experience is computed, never stored', `SELECT bio, qualifications, languages, services,
       EXTRACT(YEAR FROM CURRENT_DATE) - practising_since
         AS years_experience
  FROM doctor_profiles
 WHERE doctor_id = :doctor;`],
    ],
  },
  appointments: {
    title: 'Appointments, reviews and reminders',
    intro: 'Reviews are allowed or refused by a trigger, not by this page.',
    blocks: [
      ['trg_validate_review (BEFORE INSERT ON reviews)', `SELECT status, patient_id, doctor_id
  INTO v_status, v_patient, v_doctor
  FROM appointments WHERE appointment_id = NEW.appointment_id
   FOR SHARE;
IF v_status IS DISTINCT FROM 'completed' THEN
  RAISE EXCEPTION 'Review rejected: appointment % is not completed', ...;
END IF;`],
      ['trg_refresh_doctor_rating (AFTER INSERT)', `UPDATE doctors SET rating_count = cnt, average_rating = avg_rating
  FROM (SELECT count(*) cnt, round(avg(rating), 2) avg_rating
          FROM reviews WHERE doctor_id = NEW.doctor_id) sub
 WHERE doctor_id = NEW.doctor_id;`],
      ['Reminders created by trigger on booking', `INSERT INTO reminders (appointment_id, remind_at)
SELECT NEW.appointment_id, lower(NEW.slot) - o
  FROM unnest(ARRAY[interval '24 hours', interval '2 hours']) o
 WHERE lower(NEW.slot) - o > now();`],
    ],
  },
  medicines: {
    title: 'Medication tracker',
    intro: 'Overlap detection uses daterange operators: && (overlaps) and * (intersection).',
    blocks: [
      ['v_medication_overlaps', `SELECT a.drug_name AS drug_a, b.drug_name AS drug_b,
       a.active_range * b.active_range AS overlap_range
  FROM medications a
  JOIN medications b
    ON a.patient_id = b.patient_id
   AND a.medication_id < b.medication_id
   AND a.active_range && b.active_range;`],
      ['Daily job: fn_generate_medication_reminder_log', `INSERT INTO medication_reminder_log (medication_reminder_id, reminder_date)
SELECT mr.medication_reminder_id, CURRENT_DATE
  FROM medication_reminders mr JOIN medications m USING (medication_id)
 WHERE m.active_range @> CURRENT_DATE
   AND EXTRACT(DOW FROM CURRENT_DATE) = ANY (mr.days_of_week)
ON CONFLICT DO NOTHING;`],
      ['v_daily_adherence', `SELECT reminder_date, count(*) AS doses_scheduled,
       count(*) FILTER (WHERE taken) AS doses_taken,
       round(100.0 * count(*) FILTER (WHERE taken) / count(*), 1) AS adherence_pct
  FROM medication_reminder_log ... GROUP BY patient_id, reminder_date;`],
    ],
  },
  meals: {
    title: 'Meal plan',
    intro: 'Planned and eaten meals share one table, split by is_planned. Diet clashes are checked against patients.dietary_notes.',
    blocks: [
      ['The week', `SELECT meal_date, meal_type, description, calories, is_planned
  FROM meals
 WHERE patient_id = :pid
   AND meal_date BETWEEN :from AND :to   -- idx_meals_patient_date
 ORDER BY meal_date, meal_type;`],
    ],
  },
  wellness: {
    title: 'Wellness trends',
    intro: 'Window functions over the daily log. RANGE (not ROWS) keeps the window a real calendar week when days are skipped.',
    blocks: [
      ['fn_wellness_trend', `SELECT log_date, mood_score,
       AVG(mood_score)  OVER wk AS mood_7d,
       AVG(sleep_hours) OVER wk AS sleep_7d,
       mood_score - LAG(mood_score) OVER (ORDER BY log_date) AS change
  FROM wellness_logs
 WHERE patient_id = :pid
WINDOW wk AS (ORDER BY log_date
              RANGE BETWEEN INTERVAL '6 days' PRECEDING AND CURRENT ROW);`],
      ['fn_adherence_wellness_correlation', `SELECT corr(a.adherence_pct, w.mood_score),
       corr(a.adherence_pct, w.sleep_hours)
  FROM v_daily_adherence a
  JOIN wellness_logs w
    ON w.patient_id = a.patient_id AND w.log_date = a.reminder_date
 WHERE a.patient_id = :pid;`],
      ['Diary: one patient, newest first', `SELECT entry_date, body, created_at
  FROM diary_entries
 WHERE patient_id = :pid      -- must match the logged-in account
   AND entry_date BETWEEN :from AND :to
 ORDER BY entry_date DESC, created_at DESC;
-- idx_diary_patient_date (patient_id, entry_date DESC, created_at DESC)`],
    ],
  },
  desk: {
    title: 'Doctor desk',
    intro: 'Schedules and leave are protected by EXCLUDE constraints; status changes by a trigger.',
    blocks: [
      ['No overlapping working blocks', `CONSTRAINT no_overlapping_blocks EXCLUDE USING gist (
    doctor_id WITH =, day_of_week WITH =,
    tsrange('2000-01-01'::date + start_time,
            '2000-01-01'::date + end_time) WITH &&
)`],
      ['No overlapping leave', `CONSTRAINT no_overlapping_leave EXCLUDE USING gist (
    doctor_id WITH =, unavailable_range WITH &&
)`],
      ['trg_validate_status_change', `-- scheduled -> completed | cancelled | no_show only
IF OLD.status <> 'scheduled' THEN RAISE EXCEPTION ...;
IF NEW.status IN ('completed','no_show') AND lower(NEW.slot) > now()
THEN RAISE EXCEPTION 'Cannot mark as % before the appointment has started';`],
      ['Saving your profile (upsert)', `INSERT INTO doctor_profiles (doctor_id, bio, qualifications, ...)
VALUES (:me, :bio, :quals, ...)
ON CONFLICT (doctor_id) DO UPDATE
   SET bio = EXCLUDED.bio, qualifications = EXCLUDED.qualifications, ...;`],
    ],
  },
  hood: {
    title: 'Under the hood',
    intro: 'Every check on this page is decided by PostgreSQL. The API only translates the error into a 409 or 422.',
    blocks: [
      ['Reminder dispatcher (pg_cron, every minute)', `SELECT cron.schedule('salus_dispatch_appointment_reminders',
                     '* * * * *', $$SELECT fn_dispatch_due_reminders()$$);

-- inside: mark due reminders sent, skip rows another worker holds
WITH due AS (SELECT reminder_id FROM reminders
              WHERE sent_at IS NULL AND remind_at <= now()
              FOR UPDATE SKIP LOCKED)
UPDATE reminders SET sent_at = now() FROM due ...
-- then: pg_notify('salus_reminders', payload)`],
    ],
  },
}
