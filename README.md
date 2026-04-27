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
