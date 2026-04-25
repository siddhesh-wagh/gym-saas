from flask import Flask, jsonify, request, render_template, session, redirect
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from sqlalchemy import func
import os
import csv
import random

load_dotenv()
app = Flask(__name__)

# -----------------------
# Config
# -----------------------

app.secret_key = os.getenv("SECRET_KEY")

UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URL")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=False,   # Set True in production (HTTPS)
    SESSION_COOKIE_SAMESITE="Lax"
)

ADMIN_EMAILS = os.getenv("ADMIN_EMAILS", "").split(",")

db = SQLAlchemy(app)


# -----------------------
# Auth Decorators
# -----------------------

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "gym_id" not in session:
            if request.method in ("POST", "PUT", "DELETE") or request.is_json:
                return jsonify({"error": "Unauthorized"}), 401
            return redirect("/login")
        return f(*args, **kwargs)
    return wrapper


def role_required(role):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if session.get("role") != role:
                if request.method in ("POST", "PUT", "DELETE") or request.is_json:
                    return jsonify({"error": "Forbidden"}), 403
                return "Unauthorized", 403
            return f(*args, **kwargs)
        return wrapper
    return decorator


def owns_member(member):
    return session.get("role") == "admin" or member.gym_id == session["gym_id"]


# -----------------------
# Multi-Gym Isolation Helpers
# -----------------------

def is_admin():
    return session.get("role") == "admin"


def gym_member_filter():
    """Scope Member queries to the current gym unless admin."""
    if is_admin():
        return db.true()
    return Member.gym_id == session["gym_id"]


# -----------------------
# Audit Log Helper
# -----------------------

def log_action(action, gym_id=None):
    try:
        db.session.add(AuditLog(
            action=action,
            gym_id=gym_id or session.get("gym_id"),
            performed_by=session.get("gym_id")
        ))
    except Exception:
        pass  # Never let audit logging crash the main flow


# -----------------------
# Models
# -----------------------

class Gym(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(100))
    email      = db.Column(db.String(100), unique=True)
    password   = db.Column(db.String(255))
    role       = db.Column(db.String(20), default="gym")
    is_active  = db.Column(db.Boolean, default=True)
    is_deleted = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # SaaS subscription
    subscription_expiry = db.Column(db.Date, nullable=True)


class Plan(db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(50))
    duration_days = db.Column(db.Integer)
    is_active     = db.Column(db.Boolean, default=True)


def generate_member_id():
    return str(random.randint(1000, 9999))


class Member(db.Model):
    __table_args__ = (
        db.UniqueConstraint('phone', 'gym_id', name='unique_member_per_gym'),
        db.UniqueConstraint('email', 'gym_id', name='unique_email_per_gym'),
    )

    id        = db.Column(db.Integer, primary_key=True)
    unique_id = db.Column(db.String(10), unique=True)
    name      = db.Column(db.String(100))
    phone     = db.Column(db.String(20))
    email     = db.Column(db.String(100), nullable=True)
    age       = db.Column(db.Integer)
    gender    = db.Column(db.String(10))
    address   = db.Column(db.String(200))
    photo     = db.Column(db.String(200))

    join_date   = db.Column(db.Date)
    expiry_date = db.Column(db.Date)

    gym_id  = db.Column(db.Integer, db.ForeignKey('gym.id'))
    plan_id = db.Column(db.Integer, db.ForeignKey('plan.id'))

    history = db.relationship(
        'MembershipHistory', backref='member',
        lazy=True, cascade="all, delete-orphan"
    )


class MembershipHistory(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    member_id  = db.Column(db.Integer, db.ForeignKey('member.id'))
    plan_id    = db.Column(db.Integer, db.ForeignKey('plan.id'))
    start_date = db.Column(db.Date)
    end_date   = db.Column(db.Date)


class Payment(db.Model):
    """Payment placeholder — plug Razorpay/Stripe here later."""
    id         = db.Column(db.Integer, primary_key=True)
    gym_id     = db.Column(db.Integer, db.ForeignKey('gym.id'))
    amount     = db.Column(db.Integer)       # in paise/cents
    status     = db.Column(db.String(20))    # pending / success / failed
    reference  = db.Column(db.String(100))   # gateway order ID
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AuditLog(db.Model):
    """Track every important admin action."""
    id           = db.Column(db.Integer, primary_key=True)
    action       = db.Column(db.String(200))
    gym_id       = db.Column(db.Integer, nullable=True)
    performed_by = db.Column(db.Integer, nullable=True)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)


# -----------------------
# Public Routes
# -----------------------

@app.route("/")
def home():
    if "gym_id" in session:
        return redirect("/admin" if session.get("role") == "admin" else "/dashboard")
    return render_template("login.html")


# -----------------------
# Signup  (gym owners only — role always "gym")
# -----------------------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name     = request.form.get("name", "").strip()
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        if not name or not email or not password:
            return render_template("signup.html", error="All fields are required")

        if Gym.query.filter_by(email=email).first():
            return render_template("signup.html", error="Email already registered")

        hashed = generate_password_hash(password, method='pbkdf2:sha256', salt_length=16)
        trial_expiry = datetime.today().date() + timedelta(days=7)

        gym = Gym(name=name, email=email, password=hashed,
                  role="gym", subscription_expiry=trial_expiry)
        db.session.add(gym)
        db.session.commit()

        return redirect("/login")

    return render_template("signup.html")


# -----------------------
# Login
# -----------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        gym = Gym.query.filter_by(email=email, is_deleted=False).first()

        if not gym or not check_password_hash(gym.password, password):
            return render_template("login.html", error="Invalid email or password")

        # if gym.role == "admin" and gym.email not in ADMIN_EMAILS:
        #     return render_template("login.html", error="Invalid email or password")

        if gym.role == "gym" and not gym.is_active:
            return render_template("login.html", error="Account disabled. Contact support.")

        if gym.role == "gym" and gym.subscription_expiry:
            if gym.subscription_expiry < datetime.today().date():
                return render_template("login.html", error="Subscription expired. Please renew.")

        session["gym_id"] = gym.id
        session["role"]   = gym.role

        return redirect("/admin" if gym.role == "admin" else "/dashboard")

    return render_template("login.html")


# -----------------------
# Logout
# -----------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# -----------------------
# Gym Dashboard
# -----------------------
@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("index.html")


# -----------------------
# Admin Dashboard
# -----------------------
@app.route("/admin")
@login_required
@role_required("admin")
def admin_dashboard():
    today = datetime.today().date()
    gyms  = Gym.query.filter_by(role="gym", is_deleted=False)\
                     .order_by(Gym.created_at.desc()).all()

    member_counts = dict(
        db.session.query(Member.gym_id, func.count(Member.id))
        .group_by(Member.gym_id).all()
    )

    gym_data = [{
        "id":                  g.id,
        "name":                g.name,
        "email":               g.email,
        "is_active":           g.is_active,
        "created_at":          g.created_at.strftime("%d %b %Y") if g.created_at else "—",
        "members":             member_counts.get(g.id, 0),
        "subscription_expiry": str(g.subscription_expiry) if g.subscription_expiry else "—"
    } for g in gyms]

    return render_template(
        "admin.html",
        total_gyms=len(gyms),
        total_members=Member.query.count(),
        active_today=Member.query.filter(Member.expiry_date >= today).count(),
        gym_data=gym_data
    )


# -----------------------
# Admin — Stats API
# -----------------------
@app.route("/admin/stats")
@login_required
@role_required("admin")
def admin_stats():
    today = datetime.today().date()
    return jsonify({
        "total_gyms":      Gym.query.filter_by(role="gym", is_deleted=False).count(),
        "active_gyms":     Gym.query.filter_by(role="gym", is_active=True, is_deleted=False).count(),
        "total_members":   Member.query.count(),
        "active_members":  Member.query.filter(Member.expiry_date >= today).count(),
        "expired_members": Member.query.filter(Member.expiry_date < today).count(),
    })


# -----------------------
# Admin — Toggle Gym
# -----------------------
@app.route("/admin/toggle-gym/<int:gym_id>", methods=["POST"])
@login_required
@role_required("admin")
def toggle_gym(gym_id):
    try:
        gym = db.session.get(Gym, gym_id)
        if not gym or gym.role == "admin":
            return jsonify({"error": "Gym not found"}), 404

        gym.is_active = not gym.is_active
        log_action(f"{'Enabled' if gym.is_active else 'Disabled'} gym {gym.email}", gym_id)
        db.session.commit()

        return jsonify({"message": f"Gym {'enabled' if gym.is_active else 'disabled'}",
                        "is_active": gym.is_active})
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Something went wrong"}), 500


# -----------------------
# Admin — Soft Delete Gym
# -----------------------
@app.route("/admin/delete-gym/<int:gym_id>", methods=["DELETE"])
@login_required
@role_required("admin")
def delete_gym(gym_id):
    try:
        gym = db.session.get(Gym, gym_id)
        if not gym or gym.role == "admin":
            return jsonify({"error": "Gym not found"}), 404

        if gym.id == session["gym_id"]:
            return jsonify({"error": "Cannot delete yourself"}), 400

        gym.is_deleted = True
        gym.is_active  = False
        log_action(f"Soft-deleted gym {gym.email}", gym_id)
        db.session.commit()

        return jsonify({"message": "Gym deleted successfully"})
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Delete failed"}), 500


# -----------------------
# Admin — Renew Gym Subscription
# -----------------------
@app.route("/admin/renew-gym/<int:gym_id>", methods=["POST"])
@login_required
@role_required("admin")
def renew_gym_subscription(gym_id):
    try:
        data = request.get_json()
        days = int(data.get("days", 30))

        gym = db.session.get(Gym, gym_id)
        if not gym or gym.role == "admin":
            return jsonify({"error": "Gym not found"}), 404

        today = datetime.today().date()
        base  = max(today, gym.subscription_expiry) if gym.subscription_expiry else today
        gym.subscription_expiry = base + timedelta(days=days)
        gym.is_active = True

        log_action(f"Renewed gym {gym.email} subscription +{days} days", gym_id)
        db.session.commit()

        return jsonify({"message": "Subscription renewed",
                        "new_expiry": str(gym.subscription_expiry)})
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid days value"}), 400
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Renewal failed"}), 500


# -----------------------
# Admin — Audit Logs
# -----------------------
@app.route("/admin/audit-logs")
@login_required
@role_required("admin")
def audit_logs():
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(100).all()
    return jsonify([{
        "action":       l.action,
        "gym_id":       l.gym_id,
        "performed_by": l.performed_by,
        "created_at":   l.created_at.strftime("%d %b %Y %H:%M")
    } for l in logs])


# -----------------------
# Plans — Get All
# -----------------------
@app.route("/plans")
@login_required
def get_plans():
    plans = Plan.query.filter_by(is_active=True).all()
    return jsonify([{
        "id":            p.id,
        "name":          p.name,
        "duration_days": p.duration_days
    } for p in plans])


# -----------------------
# Plans — Admin Create
# -----------------------
@app.route("/admin/add-plan", methods=["POST"])
@login_required
@role_required("admin")
def add_plan():
    data = request.get_json()
    name = (data.get("name") or "").strip()

    try:
        duration_days = int(data.get("duration_days"))
    except (TypeError, ValueError):
        return jsonify({"error": "duration_days must be a number"}), 400

    if not name or not duration_days:
        return jsonify({"error": "Name and duration_days required"}), 400

    plan = Plan(name=name, duration_days=duration_days)
    db.session.add(plan)
    log_action(f"Created plan '{name}' ({duration_days} days)")
    db.session.commit()

    return jsonify({"message": "Plan created", "id": plan.id})


# -----------------------
# Plans — Admin Deactivate
# -----------------------
@app.route("/admin/delete-plan/<int:plan_id>", methods=["DELETE"])
@login_required
@role_required("admin")
def delete_plan(plan_id):
    plan = db.session.get(Plan, plan_id)
    if not plan:
        return jsonify({"error": "Plan not found"}), 404

    plan.is_active = False
    log_action(f"Deactivated plan '{plan.name}'")
    db.session.commit()

    return jsonify({"message": "Plan deactivated"})


# -----------------------
# Add Member
# -----------------------
@app.route("/add-member", methods=["POST"])
@login_required
def add_member():
    try:
        name    = request.form.get("name", "").strip()
        phone   = request.form.get("phone", "").strip()
        email   = request.form.get("email", "").strip().lower() or None
        age     = request.form.get("age", "").strip()
        gender  = request.form.get("gender", "").strip()
        address = request.form.get("address", "").strip()
        file    = request.files.get("photo")
        gym_id  = session["gym_id"]

        try:
            plan_id = int(request.form.get("plan_id"))
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid plan"}), 400

        if not name or not phone:
            return jsonify({"error": "Name and phone are required"}), 400

        if Member.query.filter_by(phone=phone, gym_id=gym_id).first():
            return jsonify({"error": "Phone already registered"}), 400

        if email and Member.query.filter_by(email=email, gym_id=gym_id).first():
            return jsonify({"error": "Email already registered"}), 400

        plan = db.session.get(Plan, plan_id)
        if not plan:
            return jsonify({"error": "Invalid plan"}), 400

        photo_path = None
        if file and file.filename != "":
            filename = f"{phone}.jpg"
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file.save(filepath)
            photo_path = "/" + filepath.replace("\\", "/")

        join_date   = datetime.today().date()
        expiry_date = join_date + timedelta(days=plan.duration_days)

        while True:
            unique_id = generate_member_id()
            if not Member.query.filter_by(unique_id=unique_id).first():
                break

        new_member = Member(
            unique_id=unique_id, name=name, phone=phone, email=email,
            age=int(age) if age else None, gender=gender or None,
            address=address or None, photo=photo_path,
            join_date=join_date, expiry_date=expiry_date,
            gym_id=gym_id, plan_id=plan_id
        )

        db.session.add(new_member)
        db.session.flush()

        db.session.add(MembershipHistory(
            member_id=new_member.id, plan_id=plan_id,
            start_date=join_date, end_date=expiry_date
        ))
        db.session.commit()

        return jsonify({
            "message":     "Member added successfully",
            "member_id":   unique_id,
            "expiry_date": str(expiry_date)
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# -----------------------
# Renew Membership
# -----------------------
@app.route("/renew-member", methods=["POST"])
@login_required
def renew_member():
    data = request.get_json()

    try:
        member_id = int(data.get("member_id"))
        plan_id   = int(data.get("plan_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid IDs"}), 400

    member = db.session.get(Member, member_id)
    plan   = db.session.get(Plan, plan_id)

    if not member or not plan:
        return jsonify({"error": "Member or plan not found"}), 404

    if not owns_member(member):
        return jsonify({"error": "Unauthorized"}), 403

    start_date = datetime.today().date()
    end_date   = start_date + timedelta(days=plan.duration_days)

    member.expiry_date = end_date
    member.plan_id     = plan_id

    db.session.add(MembershipHistory(
        member_id=member.id, plan_id=plan_id,
        start_date=start_date, end_date=end_date
    ))
    db.session.commit()

    return jsonify({"message": "Membership renewed", "new_expiry": str(end_date)})


# -----------------------
# Member History
# -----------------------
@app.route("/member-history/<int:member_id>")
@login_required
def member_history(member_id):
    member = db.session.get(Member, member_id)
    if not member:
        return jsonify({"error": "Member not found"}), 404

    if not owns_member(member):
        return jsonify({"error": "Unauthorized"}), 403

    history = MembershipHistory.query.filter_by(member_id=member_id).all()

    return jsonify([{
        "plan_id":    h.plan_id,
        "start_date": str(h.start_date),
        "end_date":   str(h.end_date)
    } for h in history])


# -----------------------
# Member Profile
# -----------------------
@app.route("/member/<unique_id>")
@login_required
def member_profile(unique_id):
    member = Member.query.filter_by(unique_id=unique_id).first()
    if not member:
        return "Member not found", 404

    if not owns_member(member):
        return "Unauthorized", 403

    return render_template("member.html", member=member)


# -----------------------
# Get Members
# -----------------------
@app.route("/members")
@login_required
def get_members():
    members = Member.query.filter(gym_member_filter()).all()

    return jsonify([{
        "id":          m.id,
        "unique_id":   m.unique_id,
        "name":        m.name,
        "phone":       m.phone,
        "email":       m.email,
        "age":         m.age,
        "gender":      m.gender,
        "photo":       m.photo,
        "expiry_date": str(m.expiry_date)
    } for m in members])


# -----------------------
# Delete Member
# -----------------------
@app.route("/delete-member/<int:id>", methods=["DELETE"])
@login_required
def delete_member(id):
    member = db.session.get(Member, id)
    if not member:
        return jsonify({"error": "Member not found"}), 404

    if not owns_member(member):
        return jsonify({"error": "Unauthorized"}), 403

    db.session.delete(member)
    db.session.commit()

    return jsonify({"message": "Member deleted"})


# -----------------------
# Update Member
# -----------------------
@app.route("/update-member/<int:id>", methods=["PUT"])
@login_required
def update_member(id):
    member = db.session.get(Member, id)
    if not member:
        return jsonify({"error": "Member not found"}), 404

    if not owns_member(member):
        return jsonify({"error": "Unauthorized"}), 403

    data = request.get_json()

    member.name    = data.get("name",    member.name)
    member.phone   = data.get("phone",   member.phone)
    member.email   = data.get("email",   member.email) or None
    member.gender  = data.get("gender",  member.gender)
    member.address = data.get("address", member.address)

    age = data.get("age", member.age)
    if age in ("", None, "null"):
        member.age = None
    else:
        try:
            member.age = int(age)
        except (ValueError, TypeError):
            member.age = None

    db.session.commit()
    return jsonify({"message": "Member updated successfully"})


# -----------------------
# Expiry Alerts
# -----------------------
@app.route("/expiry-alerts")
@login_required
def expiry_alerts():
    gym_id      = session["gym_id"]
    today       = datetime.today().date()
    next_3_days = today + timedelta(days=3)

    members = Member.query.filter(
        Member.gym_id == gym_id,
        Member.expiry_date >= today,
        Member.expiry_date <= next_3_days
    ).all()

    return jsonify([{
        "name":        m.name,
        "phone":       m.phone,
        "expiry_date": str(m.expiry_date)
    } for m in members])


# -----------------------
# CSV Upload
# -----------------------
@app.route("/upload-csv", methods=["POST"])
@login_required
def upload_csv():
    file   = request.files.get("file")
    gym_id = session["gym_id"]

    try:
        plan_id = int(request.form.get("plan_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid plan"}), 400

    plan = db.session.get(Plan, plan_id)
    if not plan:
        return jsonify({"error": "Plan not found"}), 404

    join_date   = datetime.today().date()
    expiry_date = join_date + timedelta(days=plan.duration_days)
    csv_data    = file.read().decode("utf-8").splitlines()
    reader      = csv.DictReader(csv_data)
    inserted, skipped = 0, 0

    for row in reader:
        phone = (row.get("phone") or "").strip()
        email = (row.get("email") or "").strip().lower() or None

        if not phone:
            skipped += 1
            continue

        if Member.query.filter_by(phone=phone, gym_id=gym_id).first() or \
           (email and Member.query.filter_by(email=email, gym_id=gym_id).first()):
            skipped += 1
            continue

        while True:
            unique_id = generate_member_id()
            if not Member.query.filter_by(unique_id=unique_id).first():
                break

        member = Member(
            unique_id=unique_id, name=row.get("name", "").strip(),
            phone=phone, email=email,
            join_date=join_date, expiry_date=expiry_date,
            gym_id=gym_id, plan_id=plan_id
        )

        db.session.add(member)
        db.session.flush()

        db.session.add(MembershipHistory(
            member_id=member.id, plan_id=plan_id,
            start_date=join_date, end_date=expiry_date
        ))
        inserted += 1

    db.session.commit()
    return jsonify({"inserted": inserted, "skipped": skipped})


# -----------------------
# Admin — View Members of a Specific Gym
# -----------------------
@app.route("/admin/gym/<int:gym_id>/members")
@login_required
@role_required("admin")
def admin_view_members(gym_id):
    gym     = db.session.get(Gym, gym_id)
    if not gym:
        return "Gym not found", 404

    members = Member.query.filter_by(gym_id=gym_id).all()
    return render_template("admin_members.html", members=members, gym=gym)


# -----------------------
# Silence Chrome DevTools probe
# -----------------------
@app.route("/.well-known/appspecific/com.chrome.devtools.json")
def devtools():
    return jsonify({}), 200


# -----------------------
# Init DB
# -----------------------
with app.app_context():
    db.create_all()


# -----------------------
# Run
# -----------------------
if __name__ == "__main__":
    app.run(debug=True)
