-- =====================================================================
-- SALUS: scheduled jobs (pg_cron)
-- =====================================================================
CREATE EXTENSION IF NOT EXISTS pg_cron;

SELECT cron.unschedule(jobid) FROM cron.job
 WHERE jobname IN ('salus_dispatch_appointment_reminders',
                   'salus_generate_medication_log',
                   'salus_dispatch_medication_reminders');

SELECT cron.schedule('salus_dispatch_appointment_reminders', '* * * * *',
                     $$SELECT fn_dispatch_due_reminders()$$);

SELECT cron.schedule('salus_generate_medication_log', '5 0 * * *',
                     $$SELECT fn_generate_medication_reminder_log(CURRENT_DATE)$$);

SELECT cron.schedule('salus_dispatch_medication_reminders', '* * * * *',
                     $$SELECT fn_generate_medication_reminder_log(CURRENT_DATE); SELECT fn_dispatch_due_medication_reminders()$$);
