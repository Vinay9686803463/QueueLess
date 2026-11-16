BEGIN;

ALTER TABLE businesses
    ADD COLUMN IF NOT EXISTS working_days SMALLINT[] NOT NULL
        DEFAULT ARRAY[0,1,2,3,4]::SMALLINT[],
    ADD COLUMN IF NOT EXISTS timezone VARCHAR(64) NOT NULL DEFAULT 'UTC',
    ADD COLUMN IF NOT EXISTS booking_interval_minutes INTEGER NOT NULL DEFAULT 15;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'businesses_booking_interval_positive'
    ) THEN
        ALTER TABLE businesses ADD CONSTRAINT businesses_booking_interval_positive
            CHECK (booking_interval_minutes > 0);
    END IF;
END $$;

COMMIT;
