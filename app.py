from flask import Flask, jsonify, request, render_template, session, redirect, Response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from sqlalchemy import func
import os, csv, io, random

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
    SESSION_COOKIE_SECURE=False,
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

def is_admin():
    return session.get("role") == "admin"

def gym_member_filter():
    if is_admin():
        return db.true()
    return Member.gym_id == session["gym_id"]

def active_gym_ids():
    return [
        g.id for g in Gym.query.filter_by(role="gym", is_deleted=False)
        .with_entities(Gym.id).all()
    ]


# -----------------------
# Activity Log Helper
# -----------------------
def log_action(action, gym_id=None, member_name=None):
    try:
        full = f"{action} — {member_name}" if member_name else action
        db.session.add(ActivityLog(
            action=full,
            gym_id=gym_id or session.get("gym_id"),
            performed_by=session.get("gym_id"),
            created_at=datetime.utcnow()
        ))
    except Exception:
        pass


# -----------------------
# Models
# -----------------------
class Gym(db.Model):
    id              = db.Column(db.Integer, primary_key=True)
    name            = db.Column(db.String(100))
    email           = db.Column(db.String(100), unique=True)
    phone           = db.Column(db.String(20), nullable=True)
    password        = db.Column(db.String(255))
    role            = db.Column(db.String(20), default="gym")
    is_active       = db.Column(db.Boolean, default=False)
    is_deleted      = db.Column(db.Boolean, default=False)
    approval_status = db.Column(db.String(20), default="pending")
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)
    subscription_expiry = db.Column(db.Date, nullable=True)


class Plan(db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(50))
    duration_days = db.Column(db.Integer)
    price         = db.Column(db.Integer, default=0)
    is_active     = db.Column(db.Boolean, default=True)
    gym_id        = db.Column(db.Integer, db.ForeignKey('gym.id'), nullable=True)


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
    id          = db.Column(db.Integer, primary_key=True)
    member_id   = db.Column(db.Integer, db.ForeignKey('member.id'))
    plan_id     = db.Column(db.Integer, db.ForeignKey('plan.id'))
    start_date  = db.Column(db.Date)
    end_date    = db.Column(db.Date)
    amount_paid = db.Column(db.Integer, default=0)


class Payment(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    gym_id     = db.Column(db.Integer, db.ForeignKey('gym.id'))
    amount     = db.Column(db.Integer)
    status     = db.Column(db.String(20))
    reference  = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ActivityLog(db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    action       = db.Column(db.String(300))
    gym_id       = db.Column(db.Integer, db.ForeignKey('gym.id'), nullable=True)
    performed_by = db.Column(db.Integer, nullable=True)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)


AuditLog = ActivityLog


# -----------------------
# Revenue Helper
# -----------------------
def gym_revenue(gym_id):
    today            = datetime.today().date()
    month_start      = today.replace(day=1)
    last_month_end   = month_start - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    year_start       = today.replace(month=1, day=1)

    def rev(start, end):
        return db.session.query(
            func.coalesce(func.sum(MembershipHistory.amount_paid), 0)
        ).join(Member, Member.id == MembershipHistory.member_id)\
         .filter(Member.gym_id == gym_id,
                 MembershipHistory.start_date >= start,
                 MembershipHistory.start_date <= end)\
         .scalar() or 0

    return {
        "this_month": rev(month_start, today),
        "last_month": rev(last_month_start, last_month_end),
        "this_year":  rev(year_start, today),
    }


# -----------------------
# Routes — Public
# -----------------------
@app.route("/")
def home():
    if "gym_id" in session:
        return redirect("/admin" if session.get("role") == "admin" else "/dashboard")
    return render_template("login.html")


# -----------------------
# Signup
# -----------------------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name     = request.form.get("name", "").strip()
        email    = request.form.get("email", "").strip().lower()
        phone    = request.form.get("phone", "").strip()
        password = request.form.get("password", "").strip()

        if not name or not email or not phone or not password:
            return render_template("signup.html", error="All fields are required")
        if len(password) < 8:
            return render_template("signup.html", error="Password must be at least 8 characters")
        if Gym.query.filter_by(email=email, is_deleted=False).first():
            return render_template("signup.html", error="Email already registered")
        if Gym.query.filter_by(phone=phone, is_deleted=False).first():
            return render_template("signup.html", error="Phone number already registered")

        hashed       = generate_password_hash(password, method='pbkdf2:sha256', salt_length=16)
        trial_expiry = datetime.today().date() + timedelta(days=7)

        gym = Gym(
            name=name, email=email, phone=phone,
            password=hashed, role="gym",
            is_active=False, approval_status="pending",
            subscription_expiry=trial_expiry
        )
        db.session.add(gym)
        db.session.flush()
        log_action(f"Gym '{name}' registered — awaiting admin approval", gym_id=gym.id)
        db.session.commit()

        return render_template("login.html",
            success="Registration successful! Your account is pending admin approval.")

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

        if gym.role == "gym":
            if gym.approval_status == "pending":
                return render_template("login.html",
                    error="Your account is pending admin approval. Please wait.")
            if gym.approval_status == "rejected":
                return render_template("login.html",
                    error="Your registration was rejected. Contact support.")
            if not gym.is_active:
                return render_template("login.html", error="Account disabled. Contact support.")
            if gym.subscription_expiry and gym.subscription_expiry < datetime.today().date():
                return render_template("login.html", error="Subscription expired. Please renew.")

        session["gym_id"]   = gym.id
        session["role"]     = gym.role
        session["gym_name"] = gym.name

        db.session.add(ActivityLog(
            action="Logged in", gym_id=gym.id,
            performed_by=gym.id, created_at=datetime.utcnow()
        ))
        db.session.commit()

        return redirect("/admin" if gym.role == "admin" else "/dashboard")

    return render_template("login.html")


# -----------------------
# Logout
# -----------------------
@app.route("/logout")
def logout():
    gym_id = session.get("gym_id")
    if gym_id:
        db.session.add(ActivityLog(
            action="Logged out", gym_id=gym_id,
            performed_by=gym_id, created_at=datetime.utcnow()
        ))
        db.session.commit()
    session.clear()
    return redirect("/login")


# -----------------------
# Gym Dashboard
# -----------------------
@app.route("/dashboard")
@login_required
def dashboard():
    gym   = db.session.get(Gym, session["gym_id"])
    today = datetime.today().date()

    sub_expiry = gym.subscription_expiry
    sub_days, sub_status = None, "none"
    if sub_expiry:
        diff       = (sub_expiry - today).days
        sub_days   = diff
        sub_status = "expired" if diff < 0 else ("warning" if diff <= 3 else "ok")

    rev = gym_revenue(gym.id)

    return render_template(
        "index.html",
        gym_name=gym.name,
        sub_expiry=str(sub_expiry) if sub_expiry else None,
        sub_days=sub_days,
        sub_status=sub_status,
        rev_this_month=rev["this_month"],
        rev_last_month=rev["last_month"],
        rev_this_year=rev["this_year"],
    )


# -----------------------
# Gym Owner Profile
# -----------------------
@app.route("/profile")
@login_required
def gym_profile():
    gym = db.session.get(Gym, session["gym_id"])
    return render_template("gym_profile.html", gym=gym)


@app.route("/profile/update", methods=["POST"])
@login_required
def update_gym_profile():
    gym  = db.session.get(Gym, session["gym_id"])
    name = request.form.get("name", "").strip()
    if name:
        gym.name = name
        session["gym_name"] = name

    new_pass = request.form.get("new_password", "").strip()
    if new_pass:
        cur_pass = request.form.get("current_password", "").strip()
        if not check_password_hash(gym.password, cur_pass):
            return render_template("gym_profile.html", gym=gym, error="Current password is wrong")
        gym.password = generate_password_hash(new_pass, method='pbkdf2:sha256', salt_length=16)

    log_action("Updated gym profile")
    db.session.commit()
    return render_template("gym_profile.html", gym=gym, success="Profile updated")


# -----------------------
# Delete ALL Members
# -----------------------
@app.route("/delete-all-members", methods=["POST"])
@login_required
def delete_all_members():
    data     = request.get_json()
    password = (data.get("password") or "").strip()
    gym_id   = session["gym_id"]

    gym = db.session.get(Gym, gym_id)
    if not check_password_hash(gym.password, password):
        return jsonify({"error": "Wrong password"}), 403

    members = Member.query.filter_by(gym_id=gym_id).all()
    count   = len(members)
    for m in members:
        db.session.delete(m)

    log_action(f"Deleted ALL {count} members (password confirmed)")
    db.session.commit()
    return jsonify({"message": f"Deleted {count} members"})


# -----------------------
# Admin Dashboard
# -----------------------
@app.route("/admin")
@login_required
@role_required("admin")
def admin_dashboard():
    today   = datetime.today().date()
    gyms    = Gym.query.filter_by(role="gym", is_deleted=False)\
                       .order_by(Gym.created_at.desc()).all()
    gym_ids = [g.id for g in gyms if g.approval_status == "approved"]

    member_counts = dict(
        db.session.query(Member.gym_id, func.count(Member.id))
        .filter(Member.gym_id.in_(gym_ids))
        .group_by(Member.gym_id).all()
    ) if gym_ids else {}

    total_members = (
        db.session.query(func.count(Member.id))
        .filter(Member.gym_id.in_(gym_ids)).scalar()
    ) if gym_ids else 0

    active_today = (
        db.session.query(func.count(Member.id))
        .filter(Member.gym_id.in_(gym_ids), Member.expiry_date >= today).scalar()
    ) if gym_ids else 0

    pending_gyms  = [g for g in gyms if g.approval_status == "pending"]
    approved_gyms = [g for g in gyms if g.approval_status == "approved"]

    gym_data = [{
        "id":                  g.id,
        "name":                g.name,
        "email":               g.email,
        "phone":               g.phone or "—",
        "is_active":           g.is_active,
        "approval_status":     g.approval_status,
        "created_at":          g.created_at.strftime("%d %b %Y") if g.created_at else "—",
        "members":             member_counts.get(g.id, 0),
        "subscription_expiry": str(g.subscription_expiry) if g.subscription_expiry else "—"
    } for g in approved_gyms]

    pending_data = [{
        "id":         g.id,
        "name":       g.name,
        "email":      g.email,
        "phone":      g.phone or "—",
        "created_at": g.created_at.strftime("%d %b %Y %H:%M") if g.created_at else "—",
    } for g in pending_gyms]

    return render_template(
        "admin.html",
        total_gyms=len(approved_gyms),
        total_members=total_members,
        active_today=active_today,
        gym_data=gym_data,
        pending_data=pending_data,
    )


# -----------------------
# Admin — Approve / Reject
# -----------------------
@app.route("/admin/approve-gym/<int:gym_id>", methods=["POST"])
@login_required
@role_required("admin")
def approve_gym(gym_id):
    gym = db.session.get(Gym, gym_id)
    if not gym:
        return jsonify({"error": "Gym not found"}), 404
    gym.approval_status = "approved"
    gym.is_active = True
    log_action(f"Admin approved gym: {gym.email}", gym_id)
    db.session.commit()
    return jsonify({"message": "Gym approved"})


@app.route("/admin/reject-gym/<int:gym_id>", methods=["POST"])
@login_required
@role_required("admin")
def reject_gym(gym_id):
    gym = db.session.get(Gym, gym_id)
    if not gym:
        return jsonify({"error": "Gym not found"}), 404
    data   = request.get_json() or {}
    reason = data.get("reason", "")
    gym.approval_status = "rejected"
    gym.is_active = False
    log_action(f"Admin rejected gym: {gym.email} — {reason}", gym_id)
    db.session.commit()
    return jsonify({"message": "Gym rejected"})


# -----------------------
# Admin — Stats
# -----------------------
@app.route("/admin/stats")
@login_required
@role_required("admin")
def admin_stats():
    today   = datetime.today().date()
    gym_ids = active_gym_ids()
    return jsonify({
        "total_gyms":     Gym.query.filter_by(role="gym", is_deleted=False, approval_status="approved").count(),
        "pending_gyms":   Gym.query.filter_by(role="gym", is_deleted=False, approval_status="pending").count(),
        "total_members":  db.session.query(func.count(Member.id)).filter(Member.gym_id.in_(gym_ids)).scalar() if gym_ids else 0,
        "active_members": db.session.query(func.count(Member.id)).filter(Member.gym_id.in_(gym_ids), Member.expiry_date >= today).scalar() if gym_ids else 0,
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
        log_action(f"Admin {'enabled' if gym.is_active else 'disabled'} gym: {gym.email}", gym_id)
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

        members = Member.query.filter_by(gym_id=gym_id).all()
        for m in members:
            db.session.delete(m)

        gym.email      = gym.email + f"__deleted_{gym.id}"
        gym.is_deleted = True
        gym.is_active  = False

        log_action(f"Admin deleted gym: {gym.name} ({len(members)} members removed)", gym_id)
        db.session.commit()
        return jsonify({"message": f"Gym deleted ({len(members)} members removed)"})
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Delete failed"}), 500


# -----------------------
# Admin — Renew Subscription
# -----------------------
@app.route("/admin/renew-gym/<int:gym_id>", methods=["POST"])
@login_required
@role_required("admin")
def renew_gym_subscription(gym_id):
    try:
        data = request.get_json()
        days = int(data.get("days", 30))
        gym  = db.session.get(Gym, gym_id)
        if not gym or gym.role == "admin":
            return jsonify({"error": "Gym not found"}), 404

        today = datetime.today().date()
        base  = max(today, gym.subscription_expiry) if gym.subscription_expiry else today
        gym.subscription_expiry = base + timedelta(days=days)
        gym.is_active = True

        log_action(f"Admin renewed gym {gym.email} subscription +{days} days", gym_id)
        db.session.commit()
        return jsonify({"message": "Subscription renewed",
                        "new_expiry": str(gym.subscription_expiry)})
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid days value"}), 400
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Renewal failed"}), 500


# -----------------------
# Admin — View Gym Members
# -----------------------
@app.route("/admin/gym/<int:gym_id>/members")
@login_required
@role_required("admin")
def admin_view_members(gym_id):
    gym = db.session.get(Gym, gym_id)
    if not gym or gym.is_deleted:
        return "Gym not found", 404
    members = Member.query.filter_by(gym_id=gym_id).all()
    rev     = gym_revenue(gym_id)
    return render_template("admin_members.html", members=members, gym=gym,
                           rev_this_month=rev["this_month"],
                           rev_last_month=rev["last_month"],
                           rev_this_year=rev["this_year"])


# -----------------------
# Activity Logs — Gym Owner
# -----------------------
@app.route("/my-logs")
@login_required
def my_logs():
    logs = ActivityLog.query.filter_by(gym_id=session["gym_id"])\
               .order_by(ActivityLog.created_at.desc()).limit(300).all()
    return jsonify([{
        "action":     l.action,
        "created_at": l.created_at.strftime("%d %b %Y %H:%M:%S")
    } for l in logs])


# -----------------------
# Activity Logs — Admin
# -----------------------
@app.route("/admin/logs")
@login_required
@role_required("admin")
def admin_logs():
    gym_filter = request.args.get("gym_id", type=int)
    q = ActivityLog.query.order_by(ActivityLog.created_at.desc())
    if gym_filter:
        q = q.filter_by(gym_id=gym_filter)
    logs      = q.limit(500).all()
    gym_names = {g.id: g.name for g in Gym.query.all()}
    return jsonify([{
        "action":     l.action,
        "gym_id":     l.gym_id,
        "gym_name":   gym_names.get(l.gym_id, "—"),
        "created_at": l.created_at.strftime("%d %b %Y %H:%M:%S")
    } for l in logs])


# -----------------------
# Plans — Get gym's plans
# -----------------------
@app.route("/plans")
@login_required
def get_plans():
    gym_id = session["gym_id"]
    plans  = Plan.query.filter_by(gym_id=gym_id, is_active=True).all()
    return jsonify([{
        "id":            p.id,
        "name":          p.name,
        "duration_days": p.duration_days,
        "price":         p.price
    } for p in plans])


# -----------------------
# Plans — Gym Owner CRUD
# -----------------------
@app.route("/gym/plans", methods=["GET"])
@login_required
def gym_plans():
    gym_id = session["gym_id"]
    plans  = Plan.query.filter_by(gym_id=gym_id, is_active=True).all()
    return jsonify([{
        "id":            p.id,
        "name":          p.name,
        "duration_days": p.duration_days,
        "price":         p.price,
        "is_custom":     True
    } for p in plans])


@app.route("/gym/plans/add", methods=["POST"])
@login_required
def gym_add_plan():
    data = request.get_json()
    name = (data.get("name") or "").strip()
    try:
        duration_days = int(data.get("duration_days", 0))
        price         = int(data.get("price", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid numbers"}), 400
    if not name:
        return jsonify({"error": "Plan name required"}), 400

    plan = Plan(name=name, duration_days=duration_days, price=price,
                gym_id=session["gym_id"])
    db.session.add(plan)
    log_action(f"Created plan '{name}' ({duration_days}d, ₹{price})")
    db.session.commit()
    return jsonify({"message": "Plan created", "id": plan.id})


@app.route("/gym/plans/update/<int:plan_id>", methods=["POST"])
@login_required
def gym_update_plan(plan_id):
    plan = db.session.get(Plan, plan_id)
    if not plan or plan.gym_id != session["gym_id"]:
        return jsonify({"error": "Plan not found or not yours"}), 404
    data = request.get_json()
    if data.get("name"):       plan.name = data["name"].strip()
    if data.get("price") is not None:
        try: plan.price = int(data["price"])
        except (ValueError, TypeError): pass
    if data.get("duration_days") is not None:
        try: plan.duration_days = int(data["duration_days"])
        except (ValueError, TypeError): pass
    log_action(f"Updated plan '{plan.name}'")
    db.session.commit()
    return jsonify({"message": "Plan updated"})


@app.route("/gym/plans/delete/<int:plan_id>", methods=["DELETE"])
@login_required
def gym_delete_plan(plan_id):
    plan = db.session.get(Plan, plan_id)
    if not plan or plan.gym_id != session["gym_id"]:
        return jsonify({"error": "Plan not found or not yours"}), 404
    plan.is_active = False
    log_action(f"Deleted plan '{plan.name}'")
    db.session.commit()
    return jsonify({"message": "Plan removed"})


# -----------------------
# Revenue API
# -----------------------
@app.route("/my-revenue")
@login_required
def my_revenue():
    return jsonify(gym_revenue(session["gym_id"]))


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
        expiry_date = (join_date + timedelta(days=plan.duration_days)
                       if plan.duration_days > 0 else join_date)

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
            start_date=join_date, end_date=expiry_date,
            amount_paid=plan.price
        ))

        log_action(f"Added member: {name} ({phone})")
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
# Renew Membership — double-submit protected
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

    today = datetime.today().date()

    # Double-submit guard — same member + plan + today already exists → skip
    existing = MembershipHistory.query.filter_by(
        member_id=member.id,
        plan_id=plan_id,
        start_date=today
    ).first()
    if existing:
        return jsonify({"message": "Membership renewed", "new_expiry": str(member.expiry_date)})

    end_date = (today + timedelta(days=plan.duration_days)
                if plan.duration_days > 0 else today)

    member.expiry_date = end_date
    member.plan_id     = plan_id

    db.session.add(MembershipHistory(
        member_id=member.id, plan_id=plan_id,
        start_date=today, end_date=end_date,
        amount_paid=plan.price
    ))

    log_action(f"Renewed membership: {member.name} — plan '{plan.name}' until {end_date}")
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

    plan_names = {p.id: p.name for p in Plan.query.all()}
    history    = MembershipHistory.query.filter_by(member_id=member_id).all()

    return jsonify([{
        "plan_id":    h.plan_id,
        "plan_name":  plan_names.get(h.plan_id, f"Plan {h.plan_id}"),
        "start_date": str(h.start_date),
        "end_date":   str(h.end_date),
        "amount":     h.amount_paid
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
    back_url = request.args.get("from", "/dashboard")
    return render_template("member.html", member=member, back_url=back_url)


# -----------------------
# Get Members (supports ?filter=active|expired|expiring&search=phone/name)
# -----------------------
@app.route("/members")
@login_required
def get_members():
    today      = datetime.today().date()
    alert_date = today + timedelta(days=3)

    q = Member.query.filter(gym_member_filter())

    # Phone/name search
    search = request.args.get("search", "").strip()
    if search:
        q = q.filter(
            db.or_(
                Member.name.ilike(f"%{search}%"),
                Member.phone.ilike(f"%{search}%")
            )
        )

    # Status filter
    status = request.args.get("filter", "")
    if status == "active":
        q = q.filter(Member.expiry_date >= today)
    elif status == "expired":
        q = q.filter(Member.expiry_date < today)
    elif status == "expiring":
        q = q.filter(Member.expiry_date >= today, Member.expiry_date <= alert_date)

    members = q.all()
    return jsonify([{
        "id":          m.id,
        "unique_id":   m.unique_id,
        "name":        m.name,
        "phone":       m.phone,
        "email":       m.email,
        "age":         m.age,
        "gender":      m.gender,
        "address":     m.address,
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
    log_action(f"Deleted member: {member.name} ({member.phone})")
    db.session.delete(member)
    db.session.commit()
    return jsonify({"message": "Member deleted"})


# -----------------------
# Update Member
# -----------------------
@app.route("/update-member/<int:id>", methods=["POST"])
@login_required
def update_member(id):
    member = db.session.get(Member, id)
    if not member:
        return jsonify({"error": "Member not found"}), 404
    if not owns_member(member):
        return jsonify({"error": "Unauthorized"}), 403

    member.name    = request.form.get("name",    member.name)
    member.phone   = request.form.get("phone",   member.phone)
    member.email   = request.form.get("email",   member.email) or None
    member.gender  = request.form.get("gender",  member.gender)
    member.address = request.form.get("address", member.address)

    age = request.form.get("age", "")
    if age not in ("", None, "null"):
        try: member.age = int(age)
        except (ValueError, TypeError): pass

    file = request.files.get("photo")
    if file and file.filename != "":
        filename = f"{member.phone}.jpg"
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)
        member.photo = "/" + filepath.replace("\\", "/")

    log_action(f"Edited member: {member.name} ({member.phone})")
    db.session.commit()
    return jsonify({"message": "Member updated successfully"})


# -----------------------
# Expiry Alerts (next 3 days)
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
    expiry_date = (join_date + timedelta(days=plan.duration_days)
                   if plan.duration_days > 0 else join_date)

    csv_data = file.read().decode("utf-8").splitlines()
    reader   = csv.DictReader(csv_data)
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
            start_date=join_date, end_date=expiry_date,
            amount_paid=plan.price
        ))
        inserted += 1

    log_action(f"CSV upload: {inserted} inserted, {skipped} skipped")
    db.session.commit()
    return jsonify({"inserted": inserted, "skipped": skipped})


# -----------------------
# Export Members — CSV
# -----------------------
@app.route("/export/members/csv")
@login_required
def export_members_csv():
    gym_id = None if is_admin() else session["gym_id"]
    q      = Member.query
    if gym_id:
        q = q.filter_by(gym_id=gym_id)
    members   = q.all()
    gym_names = {g.id: g.name for g in Gym.query.all()}

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID","Name","Phone","Email","Age","Gender",
                     "Address","Join Date","Expiry Date","Gym"])
    for m in members:
        writer.writerow([
            m.unique_id, m.name, m.phone, m.email or "",
            m.age or "", m.gender or "", m.address or "",
            m.join_date, m.expiry_date, gym_names.get(m.gym_id, "")
        ])

    log_action("Exported members as CSV")
    db.session.commit()
    return Response(output.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=members.csv"})


# -----------------------
# Export Members — JSON
# -----------------------
@app.route("/export/members/json")
@login_required
def export_members_json():
    gym_id = None if is_admin() else session["gym_id"]
    q      = Member.query
    if gym_id:
        q = q.filter_by(gym_id=gym_id)
    members   = q.all()
    gym_names = {g.id: g.name for g in Gym.query.all()}

    log_action("Exported members as Excel/JSON")
    db.session.commit()
    return jsonify([{
        "ID":        m.unique_id,
        "Name":      m.name,
        "Phone":     m.phone,
        "Email":     m.email or "",
        "Age":       m.age or "",
        "Gender":    m.gender or "",
        "Address":   m.address or "",
        "Join Date": str(m.join_date),
        "Expiry":    str(m.expiry_date),
        "Gym":       gym_names.get(m.gym_id, "")
    } for m in members])


# -----------------------
# Export Logs — JSON
# -----------------------
@app.route("/export/logs/json")
@login_required
def export_logs_json():
    if is_admin():
        gym_filter = request.args.get("gym_id", type=int)
        q = ActivityLog.query.order_by(ActivityLog.created_at.desc())
        if gym_filter:
            q = q.filter_by(gym_id=gym_filter)
        logs      = q.limit(500).all()
        gym_names = {g.id: g.name for g in Gym.query.all()}
        return jsonify([{
            "Gym":    gym_names.get(l.gym_id, "—"),
            "Action": l.action,
            "Time":   l.created_at.strftime("%d %b %Y %H:%M:%S")
        } for l in logs])
    else:
        logs = ActivityLog.query.filter_by(gym_id=session["gym_id"])\
                   .order_by(ActivityLog.created_at.desc()).limit(300).all()
        return jsonify([{
            "Action": l.action,
            "Time":   l.created_at.strftime("%d %b %Y %H:%M:%S")
        } for l in logs])


# -----------------------
# Silence Chrome DevTools
# -----------------------
@app.route("/.well-known/appspecific/com.chrome.devtools.json")
def devtools():
    return jsonify({}), 200


# -----------------------
# Init DB
# -----------------------
with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True)