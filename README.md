# VBT Dispatch

Railway deployment should treat this as a Node app.

## Railway settings
- **Root Directory**: repository root (`/`) where `package.json` lives.
- **Start Command**: `npm start`
- **Node version**: `20.x`

## Local run
# VBT Dispatch (Node + Express)

Web dispatch app for Valley Best Concrete. Includes manager and 5 drivers, PO → loads flow, driver trip workflow, approvals, ready-to-bill, monthly calendar view, and optional Google Sheets sync.

## Stack
- Node.js + Express
- PostgreSQL for store + Postgres-backed sessions (`connect-pg-simple`)
- Vanilla HTML/CSS/JS SPA in `public/index.html`

## Environment
Required:
- `DATABASE_URL`

Optional:
- `SESSION_SECRET`
- `MANAGER_PASS`, `BERYLE_PASS`, `MATTHEW_PASS`, `RIGO_PASS`, `LEONARDO_PASS`, `CARLOS_PASS`
- `SHEET_ID` + `service-account.json` for Google Sheets sync

## Run
```bash
npm install
npm start
```

## Entry file
`npm start` runs:
- `node server.js`
Open:
- `http://localhost:3000/login`

## Default users
- manager / vbt2025!
- beryle / beryle123
- matthew / matthew123
- rigo / rigo123
- leonardo / leo123
- carlos / carlos123

## Python fallback note
If you run `app.py`, it now prefers Waitress (production WSGI server) and avoids Flask debug/reloader defaults.
# Dispatch Driver App MVP

Flask + PostgreSQL MVP implementing the PO → Load → Driver → Submit → Approve → Bill flow.

## Run locally

1. Create venv and install:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. Set DB:
   ```bash
   export DATABASE_URL=postgresql://user:pass@localhost:5432/dispatch
   ```
   For quick local testing only, if `FLASK_ENV` is not `production`, the app will fall back to SQLite.
3. Start app:
   ```bash
   flask --app app run --debug
   ```

## Seeded Users

- manager / 1234
- beryle / 1234
- matthew / 1234
- rigo / 1234
- leonardo / 1234
- carlos / 1234

## Railway production safety

If `FLASK_ENV=production` and `DATABASE_URL` is missing, the app raises an error at startup.
