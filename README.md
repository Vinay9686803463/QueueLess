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
