import json
import os
import sqlite3
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, redirect, request, send_from_directory, session

BASE_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = BASE_DIR / "public"
STORE_FILE = BASE_DIR / "dispatch_store.json"
DB_FILE = BASE_DIR / "dispatch.db"

app = Flask(__name__)
app.secret_key = os.getenv("SESSION_SECRET", "vbt-dev-secret")

USERS = {
    "manager": {"username": "manager", "role": "manager", "truckId": None, "password": os.getenv("MANAGER_PASS", "vbt2025!")},
    "beryle": {"username": "beryle", "role": "driver", "truckId": "beryle", "password": os.getenv("BERYLE_PASS", "beryle123")},
    "matthew": {"username": "matthew", "role": "driver", "truckId": "matthew", "password": os.getenv("MATTHEW_PASS", "matthew123")},
    "rigo": {"username": "rigo", "role": "driver", "truckId": "rigo", "password": os.getenv("RIGO_PASS", "rigo123")},
    "leonardo": {"username": "leonardo", "role": "driver", "truckId": "leonardo", "password": os.getenv("LEONARDO_PASS", "leo123")},
    "carlos": {"username": "carlos", "role": "driver", "truckId": "carlos", "password": os.getenv("CARLOS_PASS", "carlos123")},
}

DRIVERS = ["beryle", "matthew", "rigo", "leonardo", "carlos"]
MATERIALS = ["3/4 Rock", "Sand", "Base Rock", "Drain Rock", "AB"]


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


def init_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("CREATE TABLE IF NOT EXISTS dispatch_data (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("INSERT OR IGNORE INTO dispatch_data(key, value) VALUES('store', ?)", (json.dumps({"pos": [], "loads": [], "nextPoNum": 1001, "nextLoadId": 1}),))
    conn.commit()
    conn.close()


def load_store() -> dict:
    try:
        conn = sqlite3.connect(DB_FILE)
        row = conn.execute("SELECT value FROM dispatch_data WHERE key='store'").fetchone()
        conn.close()
        if row:
            return json.loads(row[0])
    except Exception:
        pass
    if STORE_FILE.exists():
        return json.loads(STORE_FILE.read_text())
    return {"pos": [], "loads": [], "nextPoNum": 1001, "nextLoadId": 1}


def save_store(store: dict):
    payload = json.dumps(store)
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.execute("INSERT INTO dispatch_data(key, value) VALUES('store', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (payload,))
        conn.commit()
        conn.close()
    except Exception:
        STORE_FILE.write_text(payload)


def req_auth(fn):
    @wraps(fn)
    def wrap(*args, **kwargs):
        if "user" not in session:
            return jsonify({"error": "Not authenticated"}), 401
        return fn(*args, **kwargs)

    return wrap


def req_mgr(fn):
    @wraps(fn)
    def wrap(*args, **kwargs):
        user = session.get("user")
        if not user or user.get("role") != "manager":
            return jsonify({"error": "Manager only"}), 403
        return fn(*args, **kwargs)

    return wrap


def get_po(store, po_id):
    return next((p for p in store["pos"] if p["id"] == po_id), None)


def get_load(store, load_id):
    return next((l for l in store["loads"] if l["id"] == load_id), None)


def enrich(store, load):
    po = get_po(store, load["poId"]) or {}
    out = dict(load)
    out.update({
        "poNumber": po.get("poNumber"),
        "customer": po.get("customer"),
        "address": po.get("address"),
        "city": po.get("city"),
        "pickup": po.get("pickup"),
        "notes": po.get("notes"),
    })
    return out


@app.get("/healthz")
def healthz():
    return jsonify({"ok": True, "runtime": "python"})


@app.get("/public/<path:name>")
def public_file(name: str):
    return send_from_directory(PUBLIC_DIR, name)


@app.get("/login")
def login_page():
    if session.get("user"):
        return redirect("/app/")
    return send_from_directory(PUBLIC_DIR, "login.html")


@app.post("/login")
def login_action():
    username = (request.form.get("username") or "").strip().lower()
    password = request.form.get("password") or ""
    user = USERS.get(username)
    if not user or user["password"] != password:
        return "Invalid credentials. <a href='/login'>Back</a>", 401
    session["user"] = {"username": user["username"], "role": user["role"], "truckId": user["truckId"]}
    return redirect("/app/")


@app.get("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.get("/app/")
def app_page():
    if not session.get("user"):
        return redirect("/login")
    return send_from_directory(PUBLIC_DIR, "index.html")


@app.get("/api/me")
@req_auth
def api_me():
    return jsonify(session["user"])


@app.get("/api/data")
@req_auth
def api_data():
    user = session["user"]
    store = load_store()
    if user["role"] == "manager":
        loads = [enrich(store, l) for l in store["loads"] if not l.get("voided")]
    else:
        loads = [
            enrich(store, l)
            for l in store["loads"]
            if l.get("truckId") == user["truckId"] and not l.get("voided") and l.get("approvalStatus") != "approved"
        ]
    return jsonify({"trucks": DRIVERS, "materials": MATERIALS, "pos": store["pos"], "loads": loads})


@app.get("/api/my-dispatch")
@req_auth
def api_my_dispatch():
    user = session["user"]
    if user["role"] != "driver":
        return jsonify([])
    store = load_store()
    rows = [
        enrich(store, l)
        for l in store["loads"]
        if l.get("truckId") == user["truckId"] and not l.get("voided") and l.get("approvalStatus") != "approved"
    ]
    return jsonify(rows)


@app.post("/api/pos")
@req_auth
@req_mgr
def api_pos_create():
    body = request.get_json(force=True)
    store = load_store()
    po_number = body.get("poNumber") or str(store["nextPoNum"])
    if not body.get("poNumber"):
        store["nextPoNum"] += 1

    po_id = int(datetime.utcnow().timestamp() * 1000)
    po = {
        "id": po_id,
        "poNumber": po_number,
        "customer": body.get("customer", ""),
        "job": body.get("job", ""),
        "address": body.get("address", ""),
        "city": body.get("city", ""),
        "deliveryDate": body.get("deliveryDate"),
        "pickup": body.get("pickup", ""),
        "notes": body.get("notes", ""),
        "status": "open",
        "materials": body.get("assignments", []),
        "createdAt": _now(),
    }
    store["pos"].append(po)

    for assignment in body.get("assignments", []):
        qty = int(assignment.get("loadsAssigned", 1) or 1)
        for _ in range(qty):
            store["loads"].append({
                "id": store["nextLoadId"],
                "poId": po_id,
                "material": assignment.get("material", ""),
                "loadsAssigned": 1,
                "loadsDelivered": 0,
                "truckId": assignment.get("truckId") or "",
                "driverName": assignment.get("truckId") or "",
                "deliveryDate": po["deliveryDate"],
                "status": "active",
                "timestamps": {"start": None, "arrivedPickup": None, "completed": None},
                "gps": {"start": None, "arrivedPickup": None, "completed": None},
                "pod": {"signedBy": "", "signature": "", "signedAt": None},
                "ticketImage": "",
                "ticketImageAt": None,
                "approvalStatus": "pending",
                "submittedAt": None,
                "approvedAt": None,
                "approvedBy": None,
                "rejectReason": "",
                "billStatus": "not-ready",
                "billedAt": None,
                "locked": False,
                "voided": False,
                "notes": "",
            })
            store["nextLoadId"] += 1

    save_store(store)
    return jsonify({"ok": True, "po": po})


@app.put("/api/loads/<int:load_id>")
@req_auth
def api_load_update(load_id: int):
    body = request.get_json(force=True)
    store = load_store()
    load = get_load(store, load_id)
    if not load:
        return jsonify({"error": "Load not found"}), 404

    me = session["user"]
    if me["role"] != "manager" and load.get("truckId") != me.get("truckId"):
        return jsonify({"error": "Forbidden"}), 403

    if me["role"] == "driver":
        for key in ["loadsDelivered", "timestamps", "gps", "pod", "ticketImage", "ticketImageAt", "notes"]:
            if key in body:
                load[key] = body[key]
    else:
        load.update(body)

    save_store(store)
    return jsonify({"ok": True, "load": enrich(store, load)})


@app.post("/api/loads/<int:load_id>/trip-action")
@req_auth
def api_trip_action(load_id: int):
    body = request.get_json(force=True)
    action = body.get("action")
    store = load_store()
    load = get_load(store, load_id)
    if not load:
        return jsonify({"error": "Load not found"}), 404

    me = session["user"]
    if me["role"] != "manager" and load.get("truckId") != me.get("truckId"):
        return jsonify({"error": "Forbidden"}), 403

    gps = body.get("gps")
    if action == "start-trip":
        load["timestamps"]["start"] = _now()
        load["gps"]["start"] = gps
    elif action == "arrived-pickup":
        load["timestamps"]["arrivedPickup"] = _now()
        load["gps"]["arrivedPickup"] = gps
    elif action == "delivered":
        if not load["timestamps"]["start"] or not load["timestamps"]["arrivedPickup"] or not load.get("ticketImage") or not load.get("pod", {}).get("signedBy"):
            return jsonify({"error": "Cannot complete until start, arrival, ticket, and signature are captured."}), 400
        load["timestamps"]["completed"] = _now()
        load["gps"]["completed"] = gps
        load["status"] = "completed"
        load["approvalStatus"] = "submitted"
        load["submittedAt"] = _now()
        load["locked"] = True

    if body.get("ticketImage"):
        load["ticketImage"] = body["ticketImage"]
        load["ticketImageAt"] = _now()
    if body.get("pod"):
        load["pod"] = {"signedBy": body["pod"].get("signedBy", ""), "signature": body["pod"].get("signature", ""), "signedAt": _now()}

    save_store(store)
    return jsonify({"ok": True, "load": enrich(store, load)})


@app.post("/api/loads/<int:load_id>/approve")
@req_auth
@req_mgr
def api_approve(load_id: int):
    store = load_store()
    load = get_load(store, load_id)
    if not load:
        return jsonify({"error": "Load not found"}), 404
    if load.get("approvalStatus") != "submitted":
        return jsonify({"error": "Load must be submitted first"}), 400
    load["approvalStatus"] = "approved"
    load["billStatus"] = "ready"
    load["approvedAt"] = _now()
    load["approvedBy"] = session["user"]["username"]
    load["locked"] = True
    save_store(store)
    return jsonify({"ok": True, "load": enrich(store, load)})


@app.post("/api/loads/<int:load_id>/reject")
@req_auth
@req_mgr
def api_reject(load_id: int):
    body = request.get_json(force=True)
    store = load_store()
    load = get_load(store, load_id)
    if not load:
        return jsonify({"error": "Load not found"}), 404
    load["approvalStatus"] = "rejected"
    load["rejectReason"] = body.get("reason", "Rejected")
    load["locked"] = False
    load["status"] = "active"
    save_store(store)
    return jsonify({"ok": True, "load": enrich(store, load)})


@app.get("/api/ready-to-bill")
@req_auth
@req_mgr
def api_ready():
    store = load_store()
    rows = [
        enrich(store, l)
        for l in store["loads"]
        if not l.get("voided") and l.get("approvalStatus") == "approved" and l.get("billStatus") == "ready"
    ]
    month = request.args.get("month")
    if month:
        rows = [r for r in rows if str(r.get("deliveryDate") or "").startswith(month)]
    return jsonify(rows)


@app.post("/api/loads/bill")
@req_auth
@req_mgr
def api_bill():
    body = request.get_json(force=True)
    ids = {int(i) for i in body.get("ids", [])}
    store = load_store()
    changed = 0
    for load in store["loads"]:
        if load["id"] in ids and load.get("approvalStatus") == "approved" and load.get("billStatus") == "ready":
            load["billStatus"] = "billed"
            load["billedAt"] = _now()
            changed += 1
    save_store(store)
    return jsonify({"ok": True, "changed": changed})


@app.post("/api/sync")
@req_auth
@req_mgr
def api_sync():
    return jsonify({"ok": False, "error": "Google Sheets sync requires Node service. Disabled in Python runtime."}), 501


if __name__ == "__main__":
    init_db()
    port = int(os.getenv("PORT", "3000"))
    try:
        from waitress import serve

        serve(app, host="0.0.0.0", port=port)
    except Exception:
        # Fallback only when waitress is unavailable.
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
