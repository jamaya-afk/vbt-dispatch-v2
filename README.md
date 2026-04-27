# VBT Dispatch

Railway deployment should treat this as a Node app.

## Railway settings
- **Root Directory**: repository root (`/`) where `package.json` lives.
- **Start Command**: `npm start`
- **Node version**: `20.x`

## Local run
```bash
npm install
npm start
```

## Entry file
`npm start` runs:
- `node server.js`

## Default users
- manager / vbt2025!
- beryle / beryle123
- matthew / matthew123
- rigo / rigo123
- leonardo / leo123
- carlos / carlos123

## Python fallback note
If you run `app.py`, it now prefers Waitress (production WSGI server) and avoids Flask debug/reloader defaults.
