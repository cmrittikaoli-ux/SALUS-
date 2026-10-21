# SALUS: mapping the ER model to tables

Rules used (standard ER-to-relational mapping):
1. Each strong entity becomes a table; its key attribute becomes the primary key.
2. Each 1:N relationship becomes a foreign key column on the N side.
3. Total participation on the N side becomes `NOT NULL` on that foreign key.
4. The 1:0..1 relationship (appointment yields review) becomes a foreign key with a `UNIQUE` constraint.
5. The multivalued attribute `days_of_week` is stored as a PostgreSQL array (`SMALLINT[]`) with a CHECK constraint, rather than a separate table.
6. Derived attributes (`average_rating`, `rating_count`) are stored and kept current by the trigger `trg_refresh_doctor_rating`.

| Entity | Table | Primary key |
|---|---|---|
| SPECIALTY | `specialties` | `specialty_id` |
| DOCTOR | `doctors` | `doctor_id` |
| DOCTOR_SCHEDULE | `doctor_schedules` | `schedule_id` |
| DOCTOR_UNAVAILABILITY | `doctor_unavailability` | `unavailability_id` |
| PATIENT | `patients` | `patient_id` |
| APPOINTMENT | `appointments` | `appointment_id` |
| REVIEW | `reviews` | `review_id` |
| REMINDER | `reminders` | `reminder_id` |
| MEDICATION | `medications` | `medication_id` |
| MEDICATION_REMINDER | `medication_reminders` | `medication_reminder_id` |
| MEDICATION_REMINDER_LOG | `medication_reminder_log` | `log_id` |
| MEAL | `meals` | `meal_id` |
| WELLNESS_LOG | `wellness_logs` | `log_id` |

| Relationship | Cardinality | Becomes | Constraint |
|---|---|---|---|
| SPECIALTY *has* DOCTOR | 1 : N | `doctors.specialty_id` | FK, NOT NULL |
| DOCTOR *works* DOCTOR_SCHEDULE | 1 : N | `doctor_schedules.doctor_id` | FK, NOT NULL, ON DELETE CASCADE; EXCLUDE `no_overlapping_blocks` |
| DOCTOR *takes leave* DOCTOR_UNAVAILABILITY | 1 : N | `doctor_unavailability.doctor_id` | FK, NOT NULL, ON DELETE CASCADE; EXCLUDE `no_overlapping_leave` |
| DOCTOR *receives* APPOINTMENT | 1 : N | `appointments.doctor_id` | FK, NOT NULL; EXCLUDE `no_double_booking` |
| PATIENT *books* APPOINTMENT | 1 : N | `appointments.patient_id` | FK, NOT NULL |
| APPOINTMENT *yields* REVIEW | 1 : 0..1 | `reviews.appointment_id` | FK, NOT NULL, **UNIQUE**; trigger `trg_validate_review` |
| APPOINTMENT *triggers* REMINDER | 1 : N | `reminders.appointment_id` | FK, NOT NULL, ON DELETE CASCADE |
| PATIENT *tracks* MEDICATION | 1 : N | `medications.patient_id` | FK, NOT NULL |
| MEDICATION *scheduled at* MEDICATION_REMINDER | 1 : N | `medication_reminders.medication_id` | FK, NOT NULL, ON DELETE CASCADE |
| MEDICATION_REMINDER *generates* MEDICATION_REMINDER_LOG | 1 : N | `medication_reminder_log.medication_reminder_id` | FK, NOT NULL, ON DELETE CASCADE |
| PATIENT *plans* MEAL | 1 : N | `meals.patient_id` | FK, NOT NULL |
| PATIENT *records* WELLNESS_LOG | 1 : N | `wellness_logs.patient_id` | FK, NOT NULL; UNIQUE (patient_id, log_date) |

**Two deliberate extra foreign keys:** `reviews.patient_id` and `reviews.doctor_id` copy values that could be reached through the appointment. They are stored so a doctor's reviews can be read without a join. Because this redundancy could drift, the trigger `trg_validate_review` checks that both match the appointment before any review is accepted.

**Omitted from the diagram for clarity:** `created_at` audit timestamps on most tables.
