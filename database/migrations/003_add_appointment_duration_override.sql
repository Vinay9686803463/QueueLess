BEGIN;

ALTER TABLE appointments
    ADD COLUMN IF NOT EXISTS duration_minutes INTEGER;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'appointments_duration_minutes_positive'
    ) THEN
        ALTER TABLE appointments ADD CONSTRAINT appointments_duration_minutes_positive
            CHECK (duration_minutes IS NULL OR duration_minutes > 0);
    END IF;
END $$;

COMMIT;
