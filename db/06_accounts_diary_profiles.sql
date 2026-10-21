-- =====================================================================
-- SALUS: logins, patient diary, doctor profiles
-- Layered on 01_schema.sql / 02_functions.sql (needs pgcrypto from 01).
-- =====================================================================

-- ---------------------------------------------------------------------
-- 10. Accounts and login sessions
-- ---------------------------------------------------------------------
CREATE TYPE account_role AS ENUM ('patient', 'doctor');

CREATE TABLE accounts (
    account_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           TEXT NOT NULL,
    password_hash   TEXT NOT NULL,
    role            account_role NOT NULL,
    patient_id      UUID UNIQUE REFERENCES patients(patient_id) ON DELETE CASCADE,
    doctor_id       UUID UNIQUE REFERENCES doctors(doctor_id) ON DELETE CASCADE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at   TIMESTAMPTZ,

    CONSTRAINT account_owner CHECK (
        (role = 'patient' AND patient_id IS NOT NULL AND doctor_id IS NULL) OR
        (role = 'doctor'  AND doctor_id  IS NOT NULL AND patient_id IS NULL)
    )
);

CREATE UNIQUE INDEX accounts_email_key ON accounts (lower(email));

CREATE TABLE auth_sessions (
    token_hash      BYTEA PRIMARY KEY,
    account_id      UUID NOT NULL REFERENCES accounts(account_id) ON DELETE CASCADE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ NOT NULL DEFAULT now() + interval '7 days'
);

CREATE INDEX idx_auth_sessions_account ON auth_sessions (account_id);

CREATE OR REPLACE FUNCTION fn_login(p_email TEXT, p_password TEXT)
RETURNS TABLE (token TEXT, account_id UUID, role account_role, patient_id UUID, doctor_id UUID,
               expires_at TIMESTAMPTZ) AS $$
#variable_conflict use_column
DECLARE
    v       accounts%ROWTYPE;
    v_token TEXT := encode(gen_random_bytes(32), 'hex');
BEGIN
    SELECT * INTO v FROM accounts a WHERE lower(a.email) = lower(btrim(p_email));
    IF NOT FOUND OR v.password_hash <> crypt(p_password, v.password_hash) THEN
        RETURN;
    END IF;

    UPDATE accounts a SET last_login_at = now() WHERE a.account_id = v.account_id;
    DELETE FROM auth_sessions s WHERE s.account_id = v.account_id AND s.expires_at < now();

    RETURN QUERY
    INSERT INTO auth_sessions AS s (token_hash, account_id)
    VALUES (digest(v_token, 'sha256'), v.account_id)
    RETURNING v_token, v.account_id, v.role, v.patient_id, v.doctor_id, s.expires_at;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION fn_session_account(p_token TEXT)
RETURNS TABLE (account_id UUID, email TEXT, role account_role, patient_id UUID, doctor_id UUID) AS $$
    SELECT a.account_id, a.email, a.role, a.patient_id, a.doctor_id
      FROM auth_sessions s
      JOIN accounts a USING (account_id)
     WHERE s.token_hash = digest(p_token, 'sha256')
       AND s.expires_at > now();
$$ LANGUAGE sql STABLE;

CREATE OR REPLACE FUNCTION fn_create_demo_accounts(p_password TEXT) RETURNS INTEGER AS $$
DECLARE
    v_hash TEXT := crypt(p_password, gen_salt('bf', 8));
    v_patients INTEGER;
    v_doctors  INTEGER;
BEGIN
    INSERT INTO accounts (email, password_hash, role, patient_id)
    SELECT p.email, v_hash, 'patient', p.patient_id
      FROM patients p
     WHERE NOT EXISTS (SELECT 1 FROM accounts a WHERE a.patient_id = p.patient_id)
    ON CONFLICT DO NOTHING;
    GET DIAGNOSTICS v_patients = ROW_COUNT;

    INSERT INTO accounts (email, password_hash, role, doctor_id)
    SELECT d.email, v_hash, 'doctor', d.doctor_id
      FROM doctors d
     WHERE NOT EXISTS (SELECT 1 FROM accounts a WHERE a.doctor_id = d.doctor_id)
    ON CONFLICT DO NOTHING;
    GET DIAGNOSTICS v_doctors = ROW_COUNT;

    RETURN v_patients + v_doctors;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------
-- 11. Patient diary
-- ---------------------------------------------------------------------
CREATE TABLE diary_entries (
    entry_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id      UUID NOT NULL REFERENCES patients(patient_id) ON DELETE CASCADE,
    entry_date      DATE NOT NULL DEFAULT CURRENT_DATE,
    body            TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT diary_body_length CHECK (length(btrim(body)) BETWEEN 1 AND 2000)
);

CREATE INDEX idx_diary_patient_date ON diary_entries (patient_id, entry_date DESC, created_at DESC);

CREATE OR REPLACE FUNCTION fn_touch_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_diary_touch
BEFORE UPDATE ON diary_entries
FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at();

-- ---------------------------------------------------------------------
-- 12. Doctor profiles
-- ---------------------------------------------------------------------
CREATE TABLE doctor_profiles (
    doctor_id           UUID PRIMARY KEY REFERENCES doctors(doctor_id) ON DELETE CASCADE,
    bio                 TEXT CHECK (length(bio) <= 2000),
    qualifications      TEXT[] NOT NULL DEFAULT '{}',
    practising_since    SMALLINT CHECK (practising_since BETWEEN 1950 AND 2100),
    languages           TEXT[] NOT NULL DEFAULT '{}',
    services            TEXT[] NOT NULL DEFAULT '{}',
    hospital            TEXT,
    registration_no     TEXT,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_doctor_profile_touch
BEFORE UPDATE ON doctor_profiles
FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at();
