# QueueLess Backend Testing Guide

## Safety rules

- Never run integration tests against the production Supabase database.
- Always use a dedicated PostgreSQL test database.
- `TEST_DATABASE_URL` must be different from `DATABASE_URL`.
- Integration tests refuse to run when `TEST_DATABASE_URL` is missing.
- Do not reset, truncate, or delete production data.
- Do not commit or push `.env`.

## Configure the test database

1. Create a separate Supabase project or PostgreSQL database for tests.
2. Apply `database/schema.sql` and required migrations to that test database manually.
3. Add both URLs to `backend/.env`:

```env
DATABASE_URL=postgresql://user:password@production-host:5432/queueless
TEST_DATABASE_URL=postgresql://user:password@test-host:5432/queueless_test
```

4. Verify the two URLs point to different databases before running tests.

## Run safe unit and route tests

```bash
cd backend
source venv/bin/activate
python -m pytest -p no:cacheprovider
```

## Run integration tests

Integration tests are disabled by default.

```bash
cd backend
source venv/bin/activate
QUEUELESS_RUN_INTEGRATION_TESTS=1 python -m pytest -p no:cacheprovider
```

If `TEST_DATABASE_URL` is missing, the test suite refuses to start.

## Rate-limit isolation

The in-memory rate limiter is reset automatically before and after every test. This prevents rate-limit state from leaking between tests while preserving production rate limiting.