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

Open:
- `http://localhost:3000/login`

## Default users
- manager / vbt2025!
- beryle / beryle123
- matthew / matthew123
- rigo / rigo123
- leonardo / leo123
- carlos / carlos123
