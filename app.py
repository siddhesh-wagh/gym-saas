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

# Only these emails can have admin role — extra safety net
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
    """True if the session user is allowed to access this member."""
    return session.get("role") == "admin" or member.gym_id == session["gym_id"]


# -----------------------
# Models
# -----------------------

class Gym(db.Model):
    id        = db.Column(db.Integer, primary_key=True)
    name      = db.Column(db.String(100))
    email     = db.Column(db.String(100), unique=True)
    password  = db.Column(db.String(255))
    role      = db.Column(db.String(20), default="gym")   # "admin" or "gym"
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Plan(db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(50))
    duration_days = db.Column(db.Integer)


def generate_member_id():
    return str(random.randint(1000, 9999))


class Member(db.Model):
    __table_args__ = (
        db.UniqueConstraint('phone', 'gym_id', name='unique_member_per_gym'),
        db.UniqueConstraint('email', 'gym_id', name='unique_email_per_gym'),
    )

    id        = db.Column(db.Integer, primary_key=True)
    unique_id = db.Column(db.String(10), unique=True)

    name    = db.Column(db.String(100))
    phone   = db.Column(db.String(20))
    email   = db.Column(db.String(100), nullable=True)
    age     = db.Column(db.Integer)
    gender  = db.Column(db.String(10))
    address = db.Column(db.String(200))
    photo   = db.Column(db.String(200))

    join_date   = db.Column(db.Date)
    expiry_date = db.Column(db.Date)

    gym_id  = db.Column(db.Integer, db.ForeignKey('gym.id'))
    plan_id = db.Column(db.Integer, db.ForeignKey('plan.id'))

    history = db.relationship(
    'MembershipHistory',
    backref='member',
    lazy=True,
    cascade="all, delete-orphan"
)



class MembershipHistory(db.Model):
    id        = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('member.id'))
    plan_id   = db.Column(db.Integer, db.ForeignKey('plan.id'))
    start_date = db.Column(db.Date)
    end_date   = db.Column(db.Date)


# -----------------------
# Routes — Public
# -----------------------

@app.route("/")
def home():
    if "gym_id" in session:
        return redirect("/admin" if session.get("role") == "admin" else "/dashboard")
    return render_template("login.html")


# -----------------------
# Signup  (gym owners only — role always forced to "gym")
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
        gym = Gym(name=name, email=email, password=hashed, role="gym")
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

        gym = Gym.query.filter_by(email=email).first()

        # Minimal safe logging (no sensitive data)
        print(f"Login attempt for: {email}")

        # Authentication check
        if not gym or not check_password_hash(gym.password, password):
            return render_template("login.html", error="Invalid email or password")

        # Optional: Admin whitelist (keep commented if not needed)
        # if gym.role == "admin":
        #     if gym.email not in ADMIN_EMAILS:
        #         return render_template("login.html", error="Invalid email or password")

        # Block disabled gym owners
        if gym.role == "gym" and not gym.is_active:
            return render_template("login.html", error="Your account has been disabled. Contact support.")

        # Set session
        session["gym_id"] = gym.id
        session["role"]   = gym.role

        print(f"Login success: {gym.role}")

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
    # Get all gym owners
    gyms = Gym.query.filter_by(role="gym").order_by(Gym.created_at.desc()).all()

    # Stats
    total_gyms = len(gyms)
    total_members = Member.query.count()
    active_today = Member.query.filter(
        Member.expiry_date >= datetime.today().date()
    ).count()

    # Optimized member counts (NO N+1)
    member_counts = dict(
        db.session.query(Member.gym_id, func.count(Member.id))
        .group_by(Member.gym_id)
        .all()
    )

    # Prepare data for UI
    gym_data = []
    for g in gyms:
        gym_data.append({
            "id": g.id,
            "name": g.name,
            "email": g.email,
            "is_active": g.is_active,
            "created_at": g.created_at.strftime("%d %b %Y") if g.created_at else "—",
            "members": member_counts.get(g.id, 0)
        })

    return render_template(
        "admin.html",
        total_gyms=total_gyms,
        total_members=total_members,
        active_today=active_today,
        gym_data=gym_data
    )


# -----------------------
# Admin — Toggle Gym Active/Disabled
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
        db.session.commit()

        return jsonify({
            "message": f"Gym {'enabled' if gym.is_active else 'disabled'}",
            "is_active": gym.is_active
        })

    except Exception:
        db.session.rollback()
        return jsonify({"error": "Something went wrong"}), 500


# -----------------------
# Admin — Delete Gym
# -----------------------
@app.route("/admin/delete-gym/<int:gym_id>", methods=["DELETE"])
@login_required
@role_required("admin")
def delete_gym(gym_id):
    try:
        gym = db.session.get(Gym, gym_id)

        if not gym or gym.role == "admin":
            return jsonify({"error": "Gym not found"}), 404

        # Prevent deleting yourself
        if gym.id == session["gym_id"]:
            return jsonify({"error": "Cannot delete yourself"}), 400

        # Delete members (history should cascade if configured)
        Member.query.filter_by(gym_id=gym_id).delete()

        db.session.delete(gym)
        db.session.commit()

        return jsonify({"message": "Gym deleted successfully"})

    except Exception:
        db.session.rollback()
        return jsonify({"error": "Delete failed"}), 500


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
    if session.get("role") == "admin":
        members = Member.query.all()
    else:
        members = Member.query.filter_by(gym_id=session["gym_id"]).all()

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

    MembershipHistory.query.filter_by(member_id=member.id).delete()
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
            unique_id=unique_id,
            name=row.get("name", "").strip(),
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
