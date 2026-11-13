/* cspell: disable */

/*
QUEUELESS DATABASE SCHEMA
PostgreSQL / Supabase
*/

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ==========================================
-- 1. USERS
-- Business owners and staff accounts
-- ==========================================

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    full_name VARCHAR(120) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    phone VARCHAR(20),

    password_hash TEXT NOT NULL,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ==========================================
-- 2. BUSINESSES
-- ==========================================

CREATE TABLE IF NOT EXISTS businesses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    owner_id UUID NOT NULL REFERENCES users(id)
        ON DELETE RESTRICT,

    business_name VARCHAR(150) NOT NULL,
    business_type VARCHAR(80) NOT NULL,

    description TEXT,
    address TEXT,
    phone VARCHAR(20),
    email VARCHAR(255),

    opening_time TIME,
    closing_time TIME,

    average_service_time INTEGER NOT NULL DEFAULT 15
        CHECK (average_service_time > 0),

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_businesses_owner
ON businesses(owner_id);

-- ==========================================
-- 3. BUSINESS STAFF
-- Staff members assigned to businesses
-- ==========================================

CREATE TABLE IF NOT EXISTS business_staff (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    business_id UUID NOT NULL REFERENCES businesses(id)
        ON DELETE CASCADE,

    user_id UUID NOT NULL REFERENCES users(id)
        ON DELETE CASCADE,

    staff_role VARCHAR(30) NOT NULL DEFAULT 'staff'
        CHECK (staff_role IN ('staff', 'manager')),

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (business_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_business_staff_user
ON business_staff(user_id);

-- ==========================================
-- 4. SERVICES
-- Services offered by each business
-- ==========================================

CREATE TABLE IF NOT EXISTS services (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    business_id UUID NOT NULL REFERENCES businesses(id)
        ON DELETE CASCADE,

    service_name VARCHAR(120) NOT NULL,
    description TEXT,

    duration_minutes INTEGER NOT NULL DEFAULT 15
        CHECK (duration_minutes > 0),

    price NUMERIC(10, 2) NOT NULL DEFAULT 0
        CHECK (price >= 0),

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (business_id, service_name)
);

CREATE INDEX IF NOT EXISTS idx_services_business
ON services(business_id);

-- ==========================================
-- 5. APPOINTMENTS
-- Customer appointment bookings
-- ==========================================

CREATE TABLE IF NOT EXISTS customers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name VARCHAR(120) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    phone VARCHAR(20),
    password_hash TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS appointments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    business_id UUID NOT NULL REFERENCES businesses(id)
        ON DELETE CASCADE,

    service_id UUID NOT NULL REFERENCES services(id)
        ON DELETE RESTRICT,

    customer_name VARCHAR(120) NOT NULL,
    customer_phone VARCHAR(20) NOT NULL,
    customer_email VARCHAR(255),
    customer_id UUID REFERENCES customers(id) ON DELETE SET NULL,
    customer_id UUID REFERENCES customers(id) ON DELETE SET NULL,

    scheduled_at TIMESTAMPTZ NOT NULL,

    status VARCHAR(20) NOT NULL DEFAULT 'booked'
        CHECK (
            status IN (
                'booked',
                'confirmed',
                'checked_in',
                'completed',
                'cancelled',
                'no_show'
            )
        ),

    notes TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_appointments_business
ON appointments(business_id);

CREATE INDEX IF NOT EXISTS idx_appointments_schedule
ON appointments(business_id, scheduled_at);

CREATE INDEX IF NOT EXISTS idx_appointments_status
ON appointments(status);

-- ==========================================
-- 6. DAILY QUEUE COUNTERS
-- Used for safe token number allocation
-- ==========================================

CREATE TABLE IF NOT EXISTS queue_daily_counters (
    business_id UUID NOT NULL REFERENCES businesses(id)
        ON DELETE CASCADE,

    queue_date DATE NOT NULL,

    next_token_number INTEGER NOT NULL DEFAULT 1
        CHECK (next_token_number > 0),

    PRIMARY KEY (business_id, queue_date)
);

-- ==========================================
-- 7. QUEUE TOKENS
-- Walk-in and appointment queue entries
-- ==========================================

CREATE TABLE IF NOT EXISTS customers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name VARCHAR(120) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    phone VARCHAR(20),
    password_hash TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS queue_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    business_id UUID NOT NULL REFERENCES businesses(id)
        ON DELETE CASCADE,

    service_id UUID NOT NULL REFERENCES services(id)
        ON DELETE RESTRICT,

    appointment_id UUID UNIQUE REFERENCES appointments(id)
        ON DELETE SET NULL,

    customer_name VARCHAR(120) NOT NULL,
    customer_phone VARCHAR(20) NOT NULL,
    customer_id UUID REFERENCES customers(id) ON DELETE SET NULL,

    token_number INTEGER NOT NULL
        CHECK (token_number > 0),

    queue_date DATE NOT NULL DEFAULT CURRENT_DATE,

    tracking_code VARCHAR(64) NOT NULL UNIQUE
        DEFAULT encode(gen_random_bytes(16), 'hex'),

    status VARCHAR(20) NOT NULL DEFAULT 'waiting'
        CHECK (
            status IN (
                'waiting',
                'called',
                'serving',
                'completed',
                'skipped',
                'cancelled'
            )
        ),

    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    called_at TIMESTAMPTZ,
    service_started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (business_id, queue_date, token_number)
);

CREATE INDEX IF NOT EXISTS idx_queue_business_date
ON queue_tokens(business_id, queue_date);

CREATE INDEX IF NOT EXISTS idx_queue_status
ON queue_tokens(business_id, queue_date, status);

CREATE INDEX IF NOT EXISTS idx_queue_tracking
ON queue_tokens(tracking_code);

-- Password reset tokens
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ==========================================
-- 8. UPDATED_AT TRIGGER
-- Automatically updates modification time
-- ==========================================

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_users_updated_at ON users;
CREATE TRIGGER trg_users_updated_at
BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION update_updated_at();

DROP TRIGGER IF EXISTS trg_businesses_updated_at ON businesses;
CREATE TRIGGER trg_businesses_updated_at
BEFORE UPDATE ON businesses
FOR EACH ROW EXECUTE FUNCTION update_updated_at();

DROP TRIGGER IF EXISTS trg_services_updated_at ON services;
CREATE TRIGGER trg_services_updated_at
BEFORE UPDATE ON services
FOR EACH ROW EXECUTE FUNCTION update_updated_at();

DROP TRIGGER IF EXISTS trg_appointments_updated_at ON appointments;
CREATE TRIGGER trg_appointments_updated_at
BEFORE UPDATE ON appointments
FOR EACH ROW EXECUTE FUNCTION update_updated_at();

DROP TRIGGER IF EXISTS trg_queue_tokens_updated_at ON queue_tokens;
CREATE TRIGGER trg_queue_tokens_updated_at
BEFORE UPDATE ON queue_tokens
FOR EACH ROW EXECUTE FUNCTION update_updated_at();