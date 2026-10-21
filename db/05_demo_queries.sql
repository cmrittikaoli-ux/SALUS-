-- =====================================================================
-- SALUS: demo queries for the viva / report (run against the seeded DB)
-- =====================================================================
\pset pager off
\echo '\n=== 1. Multi-criteria ranking: Cardiologists near Dadar, budget 2000 ==='
SELECT full_name, distance_km, consultation_fee, average_rating, composite_score
  FROM fn_rank_doctors(19.0178, 72.8478, (SELECT specialty_id FROM specialties WHERE name = 'Cardiologist'), 2000)
 LIMIT 5;

\echo '\n=== 1b. Same search, but the patient cares only about price ==='
SELECT full_name, distance_km, consultation_fee, average_rating, composite_score
  FROM fn_rank_doctors(19.0178, 72.8478, (SELECT specialty_id FROM specialties WHERE name = 'Cardiologist'),
                       2000, 20000, 0, false, 5, 0, 1, 0);

\echo '\n=== 2. Free slots for the top-rated dermatologist, next working day ==='
SELECT slot_start, slot_end
  FROM fn_available_slots(
         (SELECT doctor_id FROM doctors d JOIN specialties s USING (specialty_id)
           WHERE s.name = 'Dermatologist' ORDER BY average_rating DESC LIMIT 1),
         CURRENT_DATE + 1)
 LIMIT 6;

\echo '\n=== 3. Concurrency: try to double-book an already-booked slot (expect an error) ==='
\echo 'For a live race, open two psql sessions, BEGIN in both, call fn_book_appointment for the same'
\echo 'doctor+slot in both: the second one blocks on the FOR UPDATE lock, then fails once the first COMMITs.'
DO $$
DECLARE a appointments;
BEGIN
    SELECT * INTO a FROM appointments WHERE status = 'scheduled' AND lower(slot) > now() LIMIT 1;
    PERFORM fn_book_appointment(
        (SELECT patient_id FROM patients WHERE patient_id <> a.patient_id LIMIT 1), a.doctor_id, lower(a.slot));
EXCEPTION WHEN exclusion_violation THEN
    RAISE NOTICE 'Blocked as expected: %', SQLERRM;
END $$;

\echo '\n=== 3b. Bypass the function and INSERT directly: the EXCLUDE constraint still refuses ==='
DO $$
DECLARE a appointments;
BEGIN
    SELECT * INTO a FROM appointments WHERE status = 'completed' LIMIT 1;
    INSERT INTO appointments (patient_id, doctor_id, slot, status)
    VALUES (a.patient_id, a.doctor_id, a.slot, 'completed');
EXCEPTION WHEN exclusion_violation THEN
    RAISE NOTICE 'Blocked by constraint no_double_booking: %', SQLERRM;
END $$;

\echo '\n=== 4. Verified reviews: reviewing a scheduled (not completed) appointment fails ==='
DO $$
DECLARE a appointments;
BEGIN
    SELECT * INTO a FROM appointments WHERE status = 'scheduled' LIMIT 1;
    INSERT INTO reviews (appointment_id, patient_id, doctor_id, rating) VALUES (a.appointment_id, a.patient_id, a.doctor_id, 5);
EXCEPTION WHEN raise_exception THEN
    RAISE NOTICE '%', SQLERRM;
END $$;

\echo '\n=== 4b. Ratings kept in sync by trigger: stored average vs recomputed ==='
SELECT d.full_name, d.average_rating AS stored, ROUND(AVG(r.rating), 2) AS recomputed, d.rating_count
  FROM doctors d JOIN reviews r USING (doctor_id)
 GROUP BY d.doctor_id ORDER BY d.average_rating DESC LIMIT 5;

\echo '\n=== 5. Reminders: queue for the next 24 hours ==='
SELECT r.remind_at, p.full_name AS patient, d.full_name AS doctor, lower(a.slot) AS appointment
  FROM reminders r JOIN appointments a USING (appointment_id)
  JOIN patients p ON p.patient_id = a.patient_id JOIN doctors d ON d.doctor_id = a.doctor_id
 WHERE r.sent_at IS NULL AND r.remind_at < now() + interval '24 hours'
 ORDER BY r.remind_at LIMIT 8;

\echo '\n=== 5b. pg_cron jobs ==='
SELECT jobname, schedule, active FROM cron.job;

\echo '\n=== 6. Interval overlap: prescriptions overlapping today ==='
SELECT p.full_name, o.drug_a, o.drug_b, o.overlap_start, COALESCE(o.overlap_end::text, 'ongoing') AS overlap_end
  FROM v_medication_overlaps o JOIN patients p USING (patient_id)
 WHERE o.overlap_range @> CURRENT_DATE
 ORDER BY p.full_name LIMIT 10;

\echo '\n=== 7. Window functions: rolling 7-day wellness for the most consistent logger ==='
SELECT * FROM fn_wellness_trend(
    (SELECT patient_id FROM wellness_logs GROUP BY patient_id ORDER BY count(*) DESC LIMIT 1),
    CURRENT_DATE - 13, CURRENT_DATE);

\echo '\n=== 7b. Adherence vs wellness (descriptive correlation), 5 patients with most data ==='
SELECT p.full_name, c.*
  FROM (SELECT a.patient_id FROM v_daily_adherence a JOIN wellness_logs w
          ON w.patient_id = a.patient_id AND w.log_date = a.reminder_date
         GROUP BY a.patient_id ORDER BY count(*) DESC LIMIT 5) t
  JOIN patients p USING (patient_id)
  CROSS JOIN LATERAL fn_adherence_wellness_correlation(t.patient_id, CURRENT_DATE - 30, CURRENT_DATE) c;

\echo '\n=== 7c. Doctor league table: RANK() within each specialty ==='
SELECT specialty, rank_in_specialty, full_name, average_rating, rating_count, completed_appointments
  FROM v_doctor_stats WHERE rank_in_specialty <= 2 ORDER BY specialty, rank_in_specialty LIMIT 12;

\echo '\n=== 8. Indexing: the planner uses the GiST index for the radius search ==='
SET enable_seqscan = off;
EXPLAIN (COSTS OFF)
SELECT doctor_id FROM doctors
 WHERE ST_DWithin(location, ST_SetSRID(ST_MakePoint(72.8478, 19.0178), 4326)::geography, 5000);
RESET enable_seqscan;
