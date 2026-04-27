const fs = require('fs');
const path = require('path');
const express = require('express');
const session = require('express-session');
const pg = require('pg');
const PgStoreFactory = require('connect-pg-simple');
const { google } = require('googleapis');

const app = express();
const PORT = Number(process.env.PORT || 3000);
const DATA_FALLBACK_FILE = path.join(__dirname, 'dispatch_store.json');
const DATABASE_URL = process.env.DATABASE_URL;
const SESSION_SECRET = process.env.SESSION_SECRET || 'vbt-hardcoded-session-secret-change-me';

if (!DATABASE_URL) {
  throw new Error('DATABASE_URL is required. Link Railway Postgres before starting.');
}

const pool = new pg.Pool({
  connectionString: DATABASE_URL,
  ssl: DATABASE_URL.includes('localhost') ? false : { rejectUnauthorized: false }
});

const PgStore = PgStoreFactory(session);

app.use(express.json({ limit: '20mb' }));
app.use(express.urlencoded({ extended: true, limit: '20mb' }));

app.use(session({
  store: new PgStore({ pool, tableName: 'user_sessions', createTableIfMissing: true }),
  secret: SESSION_SECRET,
  resave: false,
  saveUninitialized: false,
  cookie: {
    httpOnly: true,
    sameSite: 'lax',
    secure: false,
    maxAge: 1000 * 60 * 60 * 12
  }
}));

app.use('/public', express.static(path.join(__dirname, 'public')));

const users = {
  manager: { username: 'manager', role: 'manager', truckId: null, password: process.env.MANAGER_PASS || 'vbt2025!' },
  beryle: { username: 'beryle', role: 'driver', truckId: 'beryle', password: process.env.BERYLE_PASS || 'beryle123' },
  matthew: { username: 'matthew', role: 'driver', truckId: 'matthew', password: process.env.MATTHEW_PASS || 'matthew123' },
  rigo: { username: 'rigo', role: 'driver', truckId: 'rigo', password: process.env.RIGO_PASS || 'rigo123' },
  leonardo: { username: 'leonardo', role: 'driver', truckId: 'leonardo', password: process.env.LEONARDO_PASS || 'leo123' },
  carlos: { username: 'carlos', role: 'driver', truckId: 'carlos', password: process.env.CARLOS_PASS || 'carlos123' }
};

const DRIVER_ORDER = ['beryle', 'matthew', 'rigo', 'leonardo', 'carlos'];
const MATERIALS = ['3/4 Rock', 'Sand', 'Base Rock', 'Drain Rock', 'AB'];

let hasDb = true;
let store = {
  pos: [],
  loads: [],
  nextPoNum: 1001,
  nextLoadId: 1
};

function nowIso() {
  return new Date().toISOString();
}

async function ensureDataTable() {
  await pool.query(`
    CREATE TABLE IF NOT EXISTS dispatch_data (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL,
      updated_at TIMESTAMPTZ DEFAULT NOW()
    )
  `);
}

async function loadStore() {
  try {
    await ensureDataTable();
    const result = await pool.query('SELECT value FROM dispatch_data WHERE key = $1', ['store']);
    if (result.rows.length === 0) {
      await saveStore();
      return;
    }
    store = JSON.parse(result.rows[0].value);
  } catch (err) {
    console.error('[STORE] DB load failed, using fallback file', err.message);
    hasDb = false;
    if (fs.existsSync(DATA_FALLBACK_FILE)) {
      store = JSON.parse(fs.readFileSync(DATA_FALLBACK_FILE, 'utf8'));
    }
  }
}

async function saveStore() {
  const payload = JSON.stringify(store);
  if (hasDb) {
    try {
      await pool.query(
        `INSERT INTO dispatch_data (key, value, updated_at)
         VALUES ('store', $1, NOW())
         ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()`,
        [payload]
      );
      return;
    } catch (err) {
      console.error('[STORE] DB save failed; writing fallback', err.message);
      hasDb = false;
    }
  }
  fs.writeFileSync(DATA_FALLBACK_FILE, payload, 'utf8');
}

function reqAuth(req, res, next) {
  if (!req.session.user) return res.status(401).json({ error: 'Not authenticated' });
  next();
}

function reqMgr(req, res, next) {
  if (!req.session.user || req.session.user.role !== 'manager') return res.status(403).json({ error: 'Manager only' });
  next();
}

function getPoById(id) {
  return store.pos.find((p) => Number(p.id) === Number(id));
}

function getLoadById(id) {
  return store.loads.find((l) => Number(l.id) === Number(id));
}

function getStatusPill(load) {
  if (load.voided) return 'voided';
  if (load.billStatus === 'billed') return 'billed';
  if (load.approvalStatus === 'approved') return 'approved';
  if (load.approvalStatus === 'submitted') return 'submitted';
  if (load.status === 'completed') return 'delivered';
  if (load.status === 'active') return 'assigned';
  return 'assigned';
}

function enrichLoad(load) {
  const po = getPoById(load.poId) || {};
  return {
    ...load,
    poNumber: po.poNumber,
    customer: po.customer,
    address: po.address,
    city: po.city,
    pickup: po.pickup,
    notes: po.notes,
    statusPill: getStatusPill(load)
  };
}

function ensureDriverLoadAccess(req, load) {
  if (req.session.user.role === 'manager') return true;
  return load.truckId === req.session.user.truckId;
}

app.get('/healthz', async (req, res) => {
  res.json({ ok: true, hasDb });
});

app.get('/login', (req, res) => {
  if (req.session.user) return res.redirect('/app/');
  res.sendFile(path.join(__dirname, 'public', 'login.html'));
});

app.post('/login', (req, res) => {
  const username = String(req.body.username || '').trim().toLowerCase();
  const password = String(req.body.password || '');
  const user = users[username];

  console.log('[LOGIN] attempt', username);
  if (!user || user.password !== password) {
    return res.status(401).send('Invalid credentials. <a href="/login">Back</a>');
  }

  req.session.user = { username: user.username, role: user.role, truckId: user.truckId };
  return res.redirect('/app/');
});

app.get('/logout', (req, res) => {
  req.session.destroy(() => res.redirect('/login'));
});

app.get('/app/', (req, res) => {
  if (!req.session.user) return res.redirect('/login');
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

app.get('/api/me', reqAuth, (req, res) => {
  console.log('[API/me]', req.session.user);
  res.json(req.session.user);
});

app.get('/api/data', reqAuth, (req, res) => {
  const me = req.session.user;
  const loads = me.role === 'manager'
    ? store.loads.filter((l) => !l.voided)
    : store.loads.filter((l) => l.truckId === me.truckId && !l.voided && l.approvalStatus !== 'approved' && l.status !== 'completed');

  res.json({
    trucks: DRIVER_ORDER,
    materials: MATERIALS,
    pos: store.pos,
    loads: loads.map(enrichLoad)
  });
});

app.get('/api/my-dispatch', reqAuth, (req, res) => {
  const me = req.session.user;
  if (me.role !== 'driver') return res.json([]);

  const filtered = store.loads
    .filter((l) => l.truckId === me.truckId)
    .filter((l) => !l.voided)
    .filter((l) => l.approvalStatus !== 'approved')
    .filter((l) => l.status !== 'completed' || l.approvalStatus === 'submitted')
    .map(enrichLoad);

  console.log('[MY-DISPATCH]', { truckId: me.truckId, total: store.loads.length, matched: filtered.length });
  res.json(filtered);
});

app.post('/api/pos', reqAuth, reqMgr, async (req, res) => {
  const body = req.body;
  const poNumber = body.poNumber || String(store.nextPoNum++);
  const poId = Date.now();
  const po = {
    id: poId,
    poNumber,
    customer: body.customer || '',
    job: body.job || '',
    address: body.address || '',
    city: body.city || '',
    deliveryDate: body.deliveryDate,
    pickup: body.pickup || '',
    notes: body.notes || '',
    status: 'open',
    materials: body.assignments || [],
    createdAt: nowIso()
  };
  store.pos.push(po);

  const assignments = Array.isArray(body.assignments) ? body.assignments : [];
  for (const assignment of assignments) {
    const loadsAssigned = Number(assignment.loadsAssigned || 1);
    for (let i = 0; i < loadsAssigned; i += 1) {
      const load = {
        id: store.nextLoadId++,
        poId: po.id,
        material: assignment.material,
        loadsAssigned: 1,
        loadsDelivered: 0,
        truckId: assignment.truckId || '',
        driverName: assignment.truckId || '',
        deliveryDate: po.deliveryDate,
        status: 'active',
        timestamps: { start: null, arrivedPickup: null, completed: null },
        gps: { start: null, arrivedPickup: null, completed: null },
        pod: { signedBy: '', signature: '', signedAt: null },
        ticketImage: '',
        ticketImageAt: null,
        approvalStatus: 'pending',
        submittedAt: null,
        approvedAt: null,
        approvedBy: null,
        rejectReason: '',
        billStatus: 'not-ready',
        billedAt: null,
        locked: false,
        voided: false,
        notes: ''
      };
      store.loads.push(load);
    }
  }

  await saveStore();
  res.json({ ok: true, po });
});

app.put('/api/pos/:id', reqAuth, reqMgr, async (req, res) => {
  const po = getPoById(req.params.id);
  if (!po) return res.status(404).json({ error: 'PO not found' });
  Object.assign(po, req.body);
  if (req.body.deliveryDate) {
    store.loads.forEach((l) => {
      if (l.poId === po.id && !l.locked) l.deliveryDate = req.body.deliveryDate;
    });
  }
  await saveStore();
  res.json({ ok: true, po });
});

app.delete('/api/pos/:id', reqAuth, reqMgr, async (req, res) => {
  const poId = Number(req.params.id);
  const blocked = store.loads.some((l) => l.poId === poId && l.approvalStatus === 'approved');
  if (blocked) return res.status(400).json({ error: 'Cannot delete PO with approved loads' });
  store.pos = store.pos.filter((p) => Number(p.id) !== poId);
  store.loads = store.loads.filter((l) => Number(l.poId) !== poId);
  await saveStore();
  res.json({ ok: true });
});

app.put('/api/loads/:id', reqAuth, async (req, res) => {
  const load = getLoadById(req.params.id);
  if (!load) return res.status(404).json({ error: 'Load not found' });
  if (!ensureDriverLoadAccess(req, load)) return res.status(403).json({ error: 'Forbidden for this load' });
  if (load.locked && req.session.user.role !== 'manager') return res.status(400).json({ error: 'Load is locked' });

  if (req.session.user.role === 'driver') {
    const allowed = ['loadsDelivered', 'timestamps', 'gps', 'pod', 'ticketImage', 'ticketImageAt', 'notes'];
    for (const key of allowed) {
      if (key in req.body) load[key] = req.body[key];
    }
  } else {
    Object.assign(load, req.body);
  }

  await saveStore();
  res.json({ ok: true, load: enrichLoad(load) });
});

app.delete('/api/loads/:id', reqAuth, reqMgr, async (req, res) => {
  const load = getLoadById(req.params.id);
  if (!load) return res.status(404).json({ error: 'Load not found' });
  if (load.approvalStatus === 'approved') return res.status(400).json({ error: 'Approved loads cannot be deleted' });
  store.loads = store.loads.filter((l) => Number(l.id) !== Number(req.params.id));
  await saveStore();
  res.json({ ok: true });
});

app.post('/api/loads/:id/trip-action', reqAuth, async (req, res) => {
  const me = req.session.user;
  const load = getLoadById(req.params.id);
  if (!load) return res.status(404).json({ error: 'Load not found' });
  if (!ensureDriverLoadAccess(req, load)) return res.status(403).json({ error: 'Forbidden for this load' });

  const action = req.body.action;
  const gps = req.body.gps || null;

  if (action === 'start-trip') {
    load.timestamps.start = nowIso();
    load.gps.start = gps;
  }
  if (action === 'arrived-pickup') {
    load.timestamps.arrivedPickup = nowIso();
    load.gps.arrivedPickup = gps;
  }
  if (action === 'delivered') {
    const hasStart = !!load.timestamps.start;
    const hasArrived = !!load.timestamps.arrivedPickup;
    const hasTicket = !!load.ticketImage;
    const hasPod = !!(load.pod && load.pod.signedBy);
    if (!hasStart || !hasArrived || !hasTicket || !hasPod) {
      return res.status(400).json({ error: 'Cannot complete until start, arrival, ticket, and signature are captured.' });
    }
    load.timestamps.completed = nowIso();
    load.gps.completed = gps;
    load.loadsDelivered = load.loadsAssigned;
    load.status = 'completed';
    load.approvalStatus = 'submitted';
    load.submittedAt = nowIso();
    load.locked = true;
  }

  if (req.body.ticketImage) {
    load.ticketImage = req.body.ticketImage;
    load.ticketImageAt = nowIso();
  }
  if (req.body.pod) {
    load.pod = {
      signedBy: req.body.pod.signedBy || '',
      signature: req.body.pod.signature || '',
      signedAt: nowIso()
    };
  }

  if (me.role === 'driver') {
    load.driverName = me.username;
  }

  await saveStore();
  res.json({ ok: true, load: enrichLoad(load) });
});

app.post('/api/loads/:id/approve', reqAuth, reqMgr, async (req, res) => {
  const load = getLoadById(req.params.id);
  if (!load) return res.status(404).json({ error: 'Load not found' });
  if (load.approvalStatus !== 'submitted') return res.status(400).json({ error: 'Load must be submitted first' });

  load.approvalStatus = 'approved';
  load.billStatus = 'ready';
  load.approvedAt = nowIso();
  load.approvedBy = req.session.user.username;
  load.locked = true;
  await saveStore();
  res.json({ ok: true, load: enrichLoad(load) });
});

app.post('/api/loads/:id/reject', reqAuth, reqMgr, async (req, res) => {
  const load = getLoadById(req.params.id);
  if (!load) return res.status(404).json({ error: 'Load not found' });
  load.approvalStatus = 'rejected';
  load.rejectReason = String(req.body.reason || 'Rejected');
  load.locked = false;
  load.status = 'active';
  await saveStore();
  res.json({ ok: true, load: enrichLoad(load) });
});

app.get('/api/ready-to-bill', reqAuth, reqMgr, (req, res) => {
  let loads = store.loads
    .filter((l) => !l.voided)
    .filter((l) => l.approvalStatus === 'approved')
    .filter((l) => l.billStatus === 'ready')
    .map(enrichLoad);

  if (req.query.driver) loads = loads.filter((l) => l.truckId === req.query.driver);
  if (req.query.material) loads = loads.filter((l) => l.material === req.query.material);
  if (req.query.month) loads = loads.filter((l) => String(l.deliveryDate || '').startsWith(req.query.month));
  res.json(loads);
});

app.post('/api/loads/bill', reqAuth, reqMgr, async (req, res) => {
  const ids = Array.isArray(req.body.ids) ? req.body.ids.map(Number) : [];
  let changed = 0;
  for (const load of store.loads) {
    if (ids.includes(load.id) && load.approvalStatus === 'approved' && load.billStatus === 'ready') {
      load.billStatus = 'billed';
      load.billedAt = nowIso();
      changed += 1;
    }
  }
  await saveStore();
  res.json({ ok: true, changed });
});

app.post('/api/sync', reqAuth, reqMgr, async (req, res) => {
  try {
    const sheetId = process.env.SHEET_ID;
    const credsPath = path.join(__dirname, 'service-account.json');
    if (!sheetId || !fs.existsSync(credsPath)) {
      return res.status(400).json({ error: 'Missing SHEET_ID or service-account.json' });
    }

    const auth = new google.auth.GoogleAuth({
      keyFile: credsPath,
      scopes: ['https://www.googleapis.com/auth/spreadsheets']
    });
    const sheets = google.sheets({ version: 'v4', auth });

    const poRows = [['PO', 'Customer', 'Delivery Date', 'Address', 'City', 'Pickup', 'Notes']];
    for (const po of store.pos) poRows.push([po.poNumber, po.customer, po.deliveryDate, po.address, po.city, po.pickup, po.notes]);

    const loadRows = [['Load ID', 'PO', 'Driver', 'Material', 'Delivery Date', 'Approval', 'Billing']];
    for (const load of store.loads) {
      const po = getPoById(load.poId) || {};
      loadRows.push([load.id, po.poNumber || '', load.truckId, load.material, load.deliveryDate, load.approvalStatus, load.billStatus]);
    }

    await sheets.spreadsheets.values.clear({ spreadsheetId: sheetId, range: 'POs!A:Z' });
    await sheets.spreadsheets.values.update({ spreadsheetId: sheetId, range: 'POs!A1', valueInputOption: 'RAW', requestBody: { values: poRows } });
    await sheets.spreadsheets.values.clear({ spreadsheetId: sheetId, range: 'Loads!A:Z' });
    await sheets.spreadsheets.values.update({ spreadsheetId: sheetId, range: 'Loads!A1', valueInputOption: 'RAW', requestBody: { values: loadRows } });

    res.json({ ok: true, synced: { pos: poRows.length - 1, loads: loadRows.length - 1 } });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.listen(PORT, async () => {
  await loadStore();
  console.log(`VBT dispatch running on :${PORT}`);
});
