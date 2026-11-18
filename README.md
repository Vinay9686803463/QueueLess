# React + Vite
 
This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:  

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration

If you are developing a production application, we recommend using TypeScript with type-aware lint rules enabled. Check out the [TS template](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts) for information on how to integrate TypeScript and [`typescript-eslint`](https://typescript-eslint.io) in your project.
# QueueLess

## Password reset setup

Password reset OTP email is sent by the Flask backend over Gmail SMTP. Set
`MAIL_SERVER`, `MAIL_PORT`, `MAIL_USE_TLS`, `MAIL_USERNAME`, `MAIL_PASSWORD`,
and `MAIL_DEFAULT_SENDER` in `backend/.env`. Use a Gmail App Password, not your
normal Gmail password. Keep credentials in the untracked `.env` file. Delivery
fails with an explicit API error when the sender is not configured or cannot
send mail.

The existing database must have the `password_reset_otps` table. For an
existing database, apply only the `CREATE TABLE password_reset_otps` and its
three following index statements from `database/schema.sql`; do not rerun
unrelated schema changes just for password reset.

## Local admin queue demo data

The admin dashboard's **Generate 12 Demo Customers** and **Remove Demo Entries**
actions are development-only. They are available only in the Vite development
UI and when the backend has `FLASK_ENV=development`,
`QUEUELESS_ENABLE_DEMO_DATA=true`, and a local database host (`localhost`,
`127.0.0.1`, or `::1`). Demo actions are deliberately blocked for remote
databases. Never point a local development server at a production database.

Demo rows use a reserved `DEMO-` tracking-code namespace, have no customer or
appointment association, and are tagged in the dashboard. Seeding the same
business twice on the same UTC queue date is idempotent. Cleanup deletes only
the selected business's marked demo queue rows; it does not delete businesses,
services, customer accounts, appointments, or unmarked queue entries. No schema
migration is needed for demo data.

Pause/resume controls require the existing
`database/migrations/001_add_queue_paused_to_businesses.sql` migration. The

## Local demo businesses and queues

To create the eight fictional demo businesses, their four services, and twelve
waiting demo queue entries per business, first point `backend/.env` at a
dedicated local development database. Enable `QUEUELESS_ENABLE_DEMO_DATA=true`
and keep `FLASK_ENV=development`. The script rejects remote databases and does
not create or alter any admin or customer account. Use the existing active
admin email to make the demo businesses available in that admin's business
selector:

```bash
cd backend
python -m scripts.demo_businesses --dry-run
python -m scripts.demo_businesses --owner-email <admin-email>
```

Running the seed command again fills only missing marked demo businesses,
services, and today's queue entries. Demo businesses have a `DEMO ·` name and
a reserved `queueless.invalid` email; demo service descriptions and queue
tracking codes are also marked. Demo customers exist only as fictional queue
entries (no customer account records are created).

Remove the marked demo data for that admin with:

```bash
python -m scripts.demo_businesses --owner-email <admin-email> --cleanup
```

Cleanup removes only reserved demo queue entries with no customer or
appointment association, and marked demo services that are not referenced by
any queue entry or appointment. A demo business is deleted only when it has no
remaining queue entries, appointments, services, or staff; otherwise it is
preserved. The script commits seed/cleanup changes together in one transaction. The
backend reports when that migration is missing instead of indicating that the
queue is active.
