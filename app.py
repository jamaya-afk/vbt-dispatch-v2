import os
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from flask import Flask, abort, flash, redirect, render_template, request, send_file, url_for
from flask_login import LoginManager, UserMixin, current_user, login_required, login_user, logout_user
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import and_
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-change-me")

database_url = os.getenv("DATABASE_URL")
if not database_url:
    if os.getenv("FLASK_ENV") == "production":
        raise RuntimeError("DATABASE_URL is required in production. Dispatch data cannot run on temporary storage.")
    database_url = "sqlite:///dispatch_dev.db"

if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def is_active(self) -> bool:
        return self.active


class PurchaseOrder(db.Model):
    __tablename__ = "purchase_orders"

    id = db.Column(db.Integer, primary_key=True)
    po_number = db.Column(db.String(50), nullable=False, index=True)
    customer = db.Column(db.String(150), nullable=False, index=True)
    job_site_address = db.Column(db.String(250), nullable=False)
    delivery_date = db.Column(db.Date, nullable=False, index=True)
    pickup_yard = db.Column(db.String(150), nullable=False)
    notes = db.Column(db.Text)
    status = db.Column(db.String(30), default="open", nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class POMaterial(db.Model):
    __tablename__ = "po_materials"

    id = db.Column(db.Integer, primary_key=True)
    purchase_order_id = db.Column(db.Integer, db.ForeignKey("purchase_orders.id"), nullable=False, index=True)
    material_name = db.Column(db.String(120), nullable=False)
    number_of_loads = db.Column(db.Integer, nullable=False)


class LoadAssignment(db.Model):
    __tablename__ = "load_assignments"

    id = db.Column(db.Integer, primary_key=True)
    purchase_order_id = db.Column(db.Integer, db.ForeignKey("purchase_orders.id"), nullable=False, index=True)
    po_material_id = db.Column(db.Integer, db.ForeignKey("po_materials.id"), nullable=False, index=True)
    driver_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    material_name = db.Column(db.String(120), nullable=False)
    load_number = db.Column(db.Integer, nullable=False)
    total_loads_for_material = db.Column(db.Integer, nullable=False)
    delivery_date = db.Column(db.Date, nullable=False, index=True)
    pickup_yard = db.Column(db.String(150), nullable=False)
    status = db.Column(db.String(30), default="assigned", nullable=False, index=True)
    manager_notes = db.Column(db.Text)
    ticket_photo_path = db.Column(db.String(255))
    signature_path = db.Column(db.String(255))
    approved_at = db.Column(db.DateTime)
    approved_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    rejection_notes = db.Column(db.Text)
    billed_at = db.Column(db.DateTime)
    billed_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    billing_notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class TripEvent(db.Model):
    __tablename__ = "trip_events"

    id = db.Column(db.Integer, primary_key=True)
    load_assignment_id = db.Column(db.Integer, db.ForeignKey("load_assignments.id"), nullable=False, index=True)
    driver_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    event_type = db.Column(db.String(50), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False)
    gps_latitude = db.Column(db.Float)
    gps_longitude = db.Column(db.Float)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


@login_manager.user_loader
def load_user(user_id: str):
    return db.session.get(User, int(user_id))


def manager_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "manager":
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def driver_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "driver":
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def seed_users() -> None:
    users = [
        ("Manager", "manager", "manager", "1234"),
        ("Beryle", "driver", "beryle", "1234"),
        ("Matthew", "driver", "matthew", "1234"),
        ("Rigo", "driver", "rigo", "1234"),
        ("Leonardo", "driver", "leonardo", "1234"),
        ("Carlos", "driver", "carlos", "1234"),
    ]

    for name, role, username, password in users:
        existing = User.query.filter_by(username=username).first()
        if existing:
            continue
        user = User(name=name, role=role, username=username, active=True)
        user.set_password(password)
        db.session.add(user)

    db.session.commit()


with app.app_context():
    db.create_all()
    seed_users()


@app.route("/")
def home():
    if not current_user.is_authenticated:
        return redirect(url_for("login"))
    if current_user.role == "manager":
        return redirect(url_for("dispatch_board"))
    return redirect(url_for("driver_loads"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for("home"))

        flash("Invalid username or password", "error")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/manager/dispatch")
@login_required
@manager_required
def dispatch_board():
    query = db.session.query(LoadAssignment, PurchaseOrder, User).join(
        PurchaseOrder, PurchaseOrder.id == LoadAssignment.purchase_order_id
    ).outerjoin(User, User.id == LoadAssignment.driver_id)

    selected_date = request.args.get("date")
    selected_driver = request.args.get("driver")
    selected_customer = request.args.get("customer")
    selected_po = request.args.get("po")
    selected_status = request.args.get("status")

    if selected_date:
        query = query.filter(LoadAssignment.delivery_date == datetime.strptime(selected_date, "%Y-%m-%d").date())
    if selected_driver:
        query = query.filter(LoadAssignment.driver_id == int(selected_driver))
    if selected_customer:
        query = query.filter(PurchaseOrder.customer.ilike(f"%{selected_customer}%"))
    if selected_po:
        query = query.filter(PurchaseOrder.po_number.ilike(f"%{selected_po}%"))
    if selected_status:
        query = query.filter(LoadAssignment.status == selected_status)

    rows = query.order_by(LoadAssignment.delivery_date, PurchaseOrder.po_number, LoadAssignment.id).all()

    drivers = User.query.filter_by(role="driver", active=True).order_by(User.name).all()
    status_counts = {
        "unassigned": LoadAssignment.query.filter(LoadAssignment.driver_id.is_(None)).count(),
        "submitted": LoadAssignment.query.filter_by(status="submitted").count(),
        "approved": LoadAssignment.query.filter_by(status="approved").count(),
        "billed": LoadAssignment.query.filter_by(status="billed").count(),
    }

    return render_template(
        "manager_dispatch.html",
        rows=rows,
        drivers=drivers,
        status_counts=status_counts,
    )


@app.route("/manager/create-po", methods=["GET", "POST"])
@login_required
@manager_required
def create_po():
    drivers = User.query.filter_by(role="driver", active=True).order_by(User.name).all()

    if request.method == "POST":
        po = PurchaseOrder(
            po_number=request.form["po_number"],
            customer=request.form["customer"],
            job_site_address=request.form["job_site_address"],
            delivery_date=datetime.strptime(request.form["delivery_date"], "%Y-%m-%d").date(),
            pickup_yard=request.form["pickup_yard"],
            notes=request.form.get("notes", ""),
        )
        db.session.add(po)
        db.session.flush()

        material_names = request.form.getlist("material_name")
        load_counts = request.form.getlist("number_of_loads")
        assignments = request.form.getlist("driver_assignments")

        for material_name, load_count_raw, assigned_raw in zip(material_names, load_counts, assignments):
            if not material_name.strip() or not load_count_raw.strip():
                continue

            total_loads = int(load_count_raw)
            mat = POMaterial(
                purchase_order_id=po.id,
                material_name=material_name.strip(),
                number_of_loads=total_loads,
            )
            db.session.add(mat)
            db.session.flush()

            driver_usernames = [s.strip().lower() for s in assigned_raw.split(",") if s.strip()]
            driver_ids = []
            for username in driver_usernames:
                user = User.query.filter(and_(User.username == username, User.role == "driver")).first()
                if user:
                    driver_ids.append(user.id)

            for load_idx in range(1, total_loads + 1):
                driver_id = driver_ids[load_idx - 1] if load_idx - 1 < len(driver_ids) else None
                status = "assigned" if driver_id else "unassigned"
                load = LoadAssignment(
                    purchase_order_id=po.id,
                    po_material_id=mat.id,
                    driver_id=driver_id,
                    material_name=mat.material_name,
                    load_number=load_idx,
                    total_loads_for_material=total_loads,
                    delivery_date=po.delivery_date,
                    pickup_yard=po.pickup_yard,
                    status=status,
                    manager_notes=po.notes,
                )
                db.session.add(load)

        db.session.commit()
        flash("Purchase order created and loads generated.", "success")
        return redirect(url_for("dispatch_board"))

    return render_template("manager_create_po.html", drivers=drivers)


@app.route("/driver/my-loads")
@login_required
@driver_required
def driver_loads():
    loads = db.session.query(LoadAssignment, PurchaseOrder).join(
        PurchaseOrder, PurchaseOrder.id == LoadAssignment.purchase_order_id
    ).filter(
        LoadAssignment.driver_id == current_user.id,
        LoadAssignment.status.not_in(["submitted", "approved", "billed"]),
    ).order_by(LoadAssignment.delivery_date, LoadAssignment.id).all()

    return render_template("driver_loads.html", loads=loads, completed=False)


@app.route("/driver/completed")
@login_required
@driver_required
def driver_completed():
    loads = db.session.query(LoadAssignment, PurchaseOrder).join(
        PurchaseOrder, PurchaseOrder.id == LoadAssignment.purchase_order_id
    ).filter(
        LoadAssignment.driver_id == current_user.id,
        LoadAssignment.status.in_(["submitted", "approved", "billed"]),
    ).order_by(LoadAssignment.delivery_date.desc(), LoadAssignment.id.desc()).all()

    return render_template("driver_loads.html", loads=loads, completed=True)


def record_event(load: LoadAssignment, event_type: str, status: str | None = None) -> None:
    latitude = request.form.get("gps_latitude", type=float)
    longitude = request.form.get("gps_longitude", type=float)
    event = TripEvent(
        load_assignment_id=load.id,
        driver_id=current_user.id,
        event_type=event_type,
        timestamp=datetime.now(timezone.utc),
        gps_latitude=latitude,
        gps_longitude=longitude,
        notes=request.form.get("notes"),
    )
    db.session.add(event)
    if status:
        load.status = status


@app.route("/driver/load/<int:load_id>/event", methods=["POST"])
@login_required
@driver_required
def driver_event(load_id: int):
    load = LoadAssignment.query.get_or_404(load_id)
    if load.driver_id != current_user.id:
        abort(403)

    event_type = request.form["event_type"]
    status_map = {
        "started_trip": "in_progress",
        "arrived_at_yard": "in_progress",
        "ticket_uploaded": "in_progress",
        "customer_signed": "in_progress",
        "delivered": "delivered",
        "submitted_to_manager": "submitted",
    }

    if event_type not in status_map:
        abort(400)

    if event_type == "ticket_uploaded":
        file = request.files.get("ticket_photo")
        if file and file.filename:
            filename = f"load-{load.id}-ticket-{int(datetime.now().timestamp())}-{secure_filename(file.filename)}"
            filepath = UPLOAD_DIR / filename
            file.save(filepath)
            load.ticket_photo_path = str(filepath.relative_to(BASE_DIR))

    if event_type == "customer_signed":
        file = request.files.get("signature")
        if file and file.filename:
            filename = f"load-{load.id}-signature-{int(datetime.now().timestamp())}-{secure_filename(file.filename)}"
            filepath = UPLOAD_DIR / filename
            file.save(filepath)
            load.signature_path = str(filepath.relative_to(BASE_DIR))

    record_event(load, event_type, status_map[event_type])
    db.session.commit()
    return redirect(url_for("driver_loads"))


@app.route("/uploads/<path:filename>")
@login_required
def uploaded_file(filename: str):
    return send_file(BASE_DIR / "uploads" / filename)


@app.route("/manager/approvals", methods=["GET", "POST"])
@login_required
@manager_required
def approvals():
    if request.method == "POST":
        load = LoadAssignment.query.get_or_404(int(request.form["load_id"]))
        action = request.form["action"]

        if action == "approve":
            load.status = "approved"
            load.approved_at = datetime.now(timezone.utc)
            load.approved_by = current_user.id
            record = TripEvent(
                load_assignment_id=load.id,
                driver_id=load.driver_id or current_user.id,
                event_type="approved_by_manager",
                timestamp=datetime.now(timezone.utc),
            )
            db.session.add(record)
        elif action == "reject":
            load.status = "rejected"
            load.rejection_notes = request.form.get("rejection_notes")
        db.session.commit()

    rows = db.session.query(LoadAssignment, PurchaseOrder, User).join(
        PurchaseOrder, PurchaseOrder.id == LoadAssignment.purchase_order_id
    ).outerjoin(User, User.id == LoadAssignment.driver_id).filter(LoadAssignment.status == "submitted").all()

    event_map = {}
    for load, _, _ in rows:
        event_map[load.id] = TripEvent.query.filter_by(load_assignment_id=load.id).order_by(TripEvent.timestamp).all()

    return render_template("manager_approvals.html", rows=rows, event_map=event_map)


@app.route("/manager/ready-to-bill", methods=["GET", "POST"])
@login_required
@manager_required
def ready_to_bill():
    if request.method == "POST":
        load = LoadAssignment.query.get_or_404(int(request.form["load_id"]))
        billing_action = request.form["billing_action"]
        if billing_action == "billed":
            load.status = "billed"
            load.billed_at = datetime.now(timezone.utc)
            load.billed_by = current_user.id
            load.billing_notes = request.form.get("billing_notes")
        db.session.commit()

    query = db.session.query(LoadAssignment, PurchaseOrder, User).join(
        PurchaseOrder, PurchaseOrder.id == LoadAssignment.purchase_order_id
    ).outerjoin(User, User.id == LoadAssignment.driver_id).filter(LoadAssignment.status == "approved")

    customer = request.args.get("customer")
    po = request.args.get("po")
    driver = request.args.get("driver")
    material = request.args.get("material")
    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")

    if customer:
        query = query.filter(PurchaseOrder.customer.ilike(f"%{customer}%"))
    if po:
        query = query.filter(PurchaseOrder.po_number.ilike(f"%{po}%"))
    if driver:
        query = query.filter(User.name.ilike(f"%{driver}%"))
    if material:
        query = query.filter(LoadAssignment.material_name.ilike(f"%{material}%"))
    if from_date:
        query = query.filter(LoadAssignment.delivery_date >= datetime.strptime(from_date, "%Y-%m-%d").date())
    if to_date:
        query = query.filter(LoadAssignment.delivery_date <= datetime.strptime(to_date, "%Y-%m-%d").date())

    rows = query.order_by(LoadAssignment.delivery_date, PurchaseOrder.po_number).all()
    return render_template("manager_ready_to_bill.html", rows=rows)


@app.route("/manager/google-sync")
@login_required
@manager_required
def google_sync():
    rows = db.session.query(LoadAssignment, PurchaseOrder, User).join(
        PurchaseOrder, PurchaseOrder.id == LoadAssignment.purchase_order_id
    ).outerjoin(User, User.id == LoadAssignment.driver_id).filter(LoadAssignment.status.in_(["approved", "billed"])).all()

    lines = [
        "PO number,Customer,Job site,Delivery date,Driver,Material,Load number,Pickup yard,Start trip,Arrived at yard,Delivered,Submitted,Approved,Ticket photo,Signature,Billing status"
    ]

    for load, po, driver in rows:
        events = TripEvent.query.filter_by(load_assignment_id=load.id).all()
        event_lookup = {evt.event_type: evt.timestamp.isoformat() for evt in events}
        line = [
            po.po_number,
            po.customer,
            po.job_site_address,
            po.delivery_date.isoformat(),
            driver.name if driver else "",
            load.material_name,
            str(load.load_number),
            load.pickup_yard,
            event_lookup.get("started_trip", ""),
            event_lookup.get("arrived_at_yard", ""),
            event_lookup.get("delivered", ""),
            event_lookup.get("submitted_to_manager", ""),
            load.approved_at.isoformat() if load.approved_at else "",
            load.ticket_photo_path or "",
            load.signature_path or "",
            load.status,
        ]
        lines.append(",".join([str(value).replace(",", " ") for value in line]))

    output_path = BASE_DIR / "uploads" / f"google-sync-{int(datetime.now().timestamp())}.csv"
    output_path.write_text("\n".join(lines), encoding="utf-8")
    flash("Google Sheets sync export generated (CSV for reporting handoff).", "success")
    return send_file(output_path, as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
