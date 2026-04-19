from flask import Flask, jsonify, request, render_template, session, redirect
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
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

db = SQLAlchemy(app)

# -----------------------
# Helper
# -----------------------

def login_required():
    return "gym_id" in session


# -----------------------
# Models
# -----------------------

class Gym(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(255))
    role = db.Column(db.String(20), default="gym")  # "admin" or "gym"


class Plan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50))
    duration_days = db.Column(db.Integer)


def generate_member_id():
    return str(random.randint(1000, 9999))


class Member(db.Model):
    __table_args__ = (
        db.UniqueConstraint('phone', 'gym_id', name='unique_member_per_gym'),
        db.UniqueConstraint('email', 'gym_id', name='unique_email_per_gym'),
    )

    id = db.Column(db.Integer, primary_key=True)
    unique_id = db.Column(db.String(10), unique=True)

    name = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100), nullable=True)

    age = db.Column(db.Integer)
    gender = db.Column(db.String(10))
    address = db.Column(db.String(200))
    photo = db.Column(db.String(200))

    join_date = db.Column(db.Date)
    expiry_date = db.Column(db.Date)

    gym_id = db.Column(db.Integer, db.ForeignKey('gym.id'))
    plan_id = db.Column(db.Integer, db.ForeignKey('plan.id'))

    history = db.relationship('MembershipHistory', backref='member', lazy=True)


class MembershipHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    member_id = db.Column(db.Integer, db.ForeignKey('member.id'))
    plan_id = db.Column(db.Integer, db.ForeignKey('plan.id'))

    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)


# -----------------------
# Routes
# -----------------------

@app.route("/")
def home():
    if "gym_id" in session:
        if session.get("role") == "admin":
            return redirect("/admin")
        return redirect("/dashboard")
    return render_template("login.html")


# -----------------------
# Signup
# -----------------------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")

        if Gym.query.filter_by(email=email).first():
            return "Email already exists"

        hashed_password = generate_password_hash(password)
        gym = Gym(name=name, email=email, password=hashed_password, role="gym")
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
        email = request.form.get("email")
        password = request.form.get("password")

        gym = Gym.query.filter_by(email=email).first()

        if not gym or not check_password_hash(gym.password, password):
            return "Invalid credentials"

        session["gym_id"] = gym.id
        session["role"] = gym.role

        if gym.role == "admin":
            return redirect("/admin")
        else:
            return redirect("/dashboard")

    return render_template("login.html")


# -----------------------
# Logout
# -----------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# -----------------------
# Dashboard
# -----------------------
@app.route("/dashboard")
def dashboard():
    if not login_required():
        return redirect("/login")

    return render_template("index.html")


# -----------------------
# Admin Dashboard
# -----------------------
@app.route("/admin")
def admin_dashboard():
    if not login_required():
        return redirect("/login")

    if session.get("role") != "admin":
        return "Unauthorized", 403

    return render_template("admin.html")


# -----------------------
# Add Member
# -----------------------
@app.route("/add-member", methods=["POST"])
def add_member():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 401

    try:
        name = request.form.get("name")
        phone = request.form.get("phone")
        email = request.form.get("email")
        age = request.form.get("age")
        gender = request.form.get("gender")
        address = request.form.get("address")

        gym_id = session["gym_id"]
        plan_id = int(request.form.get("plan_id"))

        file = request.files.get("photo")

        if not name or not phone:
            return jsonify({"error": "Name and phone required"}), 400

        if Member.query.filter_by(phone=phone, gym_id=gym_id).first():
            return jsonify({"error": "Phone already exists"}), 400

        if email and Member.query.filter_by(email=email, gym_id=gym_id).first():
            return jsonify({"error": "Email already exists"}), 400

        plan = db.session.get(Plan, plan_id)
        if not plan:
            return jsonify({"error": "Invalid plan"}), 400

        photo_path = None
        if file and file.filename != "":
            filename = f"{phone}.jpg"
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file.save(filepath)
            photo_path = "/" + filepath.replace("\\", "/")

        join_date = datetime.today().date()
        expiry_date = join_date + timedelta(days=plan.duration_days)

        while True:
            unique_id = generate_member_id()
            if not Member.query.filter_by(unique_id=unique_id).first():
                break

        new_member = Member(
            unique_id=unique_id,
            name=name,
            phone=phone,
            email=email,
            age=int(age) if age else None,
            gender=gender,
            address=address,
            photo=photo_path,
            join_date=join_date,
            expiry_date=expiry_date,
            gym_id=gym_id,
            plan_id=plan_id
        )

        db.session.add(new_member)
        db.session.flush()

        history = MembershipHistory(
            member_id=new_member.id,
            plan_id=plan_id,
            start_date=join_date,
            end_date=expiry_date
        )

        db.session.add(history)
        db.session.commit()

        return jsonify({
            "message": "Member added successfully",
            "member_id": unique_id,
            "expiry_date": str(expiry_date)
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# -----------------------
# Renew Membership
# -----------------------
@app.route("/renew-member", methods=["POST"])
def renew_member():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()

    member_id = data.get("member_id")
    plan_id = data.get("plan_id")

    member = db.session.get(Member, member_id)
    plan = db.session.get(Plan, plan_id)

    if not member or not plan:
        return jsonify({"error": "Invalid member or plan"}), 400

    if session.get("role") != "admin" and member.gym_id != session["gym_id"]:
        return jsonify({"error": "Unauthorized"}), 403

    start_date = datetime.today().date()
    end_date = start_date + timedelta(days=plan.duration_days)

    member.expiry_date = end_date
    member.plan_id = plan_id

    history = MembershipHistory(
        member_id=member.id,
        plan_id=plan_id,
        start_date=start_date,
        end_date=end_date
    )

    db.session.add(history)
    db.session.commit()

    return jsonify({
        "message": "Membership renewed",
        "new_expiry": str(end_date)
    })


# -----------------------
# Member History
# -----------------------
@app.route("/member-history/<int:member_id>")
def member_history(member_id):
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 401

    member = db.session.get(Member, member_id)
    if not member:
        return jsonify({"error": "Member not found"}), 404

    if session.get("role") != "admin" and member.gym_id != session["gym_id"]:
        return jsonify({"error": "Unauthorized"}), 403

    history = MembershipHistory.query.filter_by(member_id=member_id).all()

    result = []
    for h in history:
        result.append({
            "plan_id": h.plan_id,
            "start_date": str(h.start_date),
            "end_date": str(h.end_date)
        })

    return jsonify(result)


# -----------------------
# Member Profile
# -----------------------
@app.route("/member/<unique_id>")
def member_profile(unique_id):
    if not login_required():
        return redirect("/login")

    member = Member.query.filter_by(unique_id=unique_id).first()

    if not member:
        return "Member not found", 404

    if session.get("role") != "admin" and member.gym_id != session["gym_id"]:
        return "Unauthorized", 403

    return render_template("member.html", member=member)


# -----------------------
# Get Members
# -----------------------
@app.route("/members/<int:gym_id>")
def get_members(gym_id):
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 401

    if session.get("role") != "admin" and session["gym_id"] != gym_id:
        return jsonify({"error": "Unauthorized"}), 403

    if session.get("role") == "admin":
        members = Member.query.all()
    else:
        members = Member.query.filter_by(gym_id=gym_id).all()

    result = []
    for m in members:
        result.append({
            "id": m.id,
            "unique_id": m.unique_id,
            "name": m.name,
            "phone": m.phone,
            "email": m.email,
            "age": m.age,
            "gender": m.gender,
            "photo": m.photo,
            "expiry_date": str(m.expiry_date)
        })

    return jsonify(result)


# -----------------------
# Delete Member
# -----------------------
@app.route("/delete-member/<int:id>", methods=["DELETE"])
def delete_member(id):
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 401

    member = db.session.get(Member, id)

    if not member:
        return jsonify({"error": "Member not found"}), 404

    if session.get("role") != "admin" and member.gym_id != session["gym_id"]:
        return jsonify({"error": "Unauthorized"}), 403

    db.session.delete(member)
    db.session.commit()

    return jsonify({"message": "Member deleted"})


# -----------------------
# Update Member
# -----------------------
@app.route("/update-member/<int:id>", methods=["PUT"])
def update_member(id):
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 401

    member = db.session.get(Member, id)

    if not member:
        return jsonify({"error": "Member not found"}), 404

    if session.get("role") != "admin" and member.gym_id != session["gym_id"]:
        return jsonify({"error": "Unauthorized"}), 403

    data = request.get_json()

    member.name = data.get("name", member.name)
    member.phone = data.get("phone", member.phone)
    member.email = data.get("email", member.email)

    age = data.get("age", member.age)
    if age == "" or age is None or age == "null":
        member.age = None
    else:
        try:
            member.age = int(age)
        except ValueError:
            member.age = None

    member.gender = data.get("gender", member.gender)
    member.address = data.get("address", member.address)

    db.session.commit()

    return jsonify({"message": "Member updated successfully"})


# -----------------------
# Expiry Alerts
# -----------------------
@app.route("/expiry-alerts/<int:gym_id>")
def expiry_alerts(gym_id):
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 401

    if session.get("role") != "admin" and session["gym_id"] != gym_id:
        return jsonify({"error": "Unauthorized"}), 403

    today = datetime.today().date()
    next_3_days = today + timedelta(days=3)

    members = Member.query.filter(
        Member.gym_id == gym_id,
        Member.expiry_date >= today,
        Member.expiry_date <= next_3_days
    ).all()

    result = []
    for m in members:
        result.append({
            "name": m.name,
            "phone": m.phone,
            "expiry_date": str(m.expiry_date)
        })

    return jsonify(result)


# -----------------------
# CSV Upload
# -----------------------
@app.route("/upload-csv", methods=["POST"])
def upload_csv():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 401

    file = request.files.get("file")
    gym_id = session["gym_id"]
    plan_id = int(request.form.get("plan_id"))

    plan = db.session.get(Plan, plan_id)
    if not plan:
        return jsonify({"error": "Invalid plan"}), 400

    join_date = datetime.today().date()
    expiry_date = join_date + timedelta(days=plan.duration_days)

    csv_data = file.read().decode("utf-8").splitlines()
    reader = csv.DictReader(csv_data)

    inserted, skipped = 0, 0

    for row in reader:
        phone = row.get("phone")
        email = row.get("email")

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
            name=row.get("name"),
            phone=phone,
            email=email,
            join_date=join_date,
            expiry_date=expiry_date,
            gym_id=gym_id,
            plan_id=plan_id
        )

        db.session.add(member)
        db.session.flush()

        history = MembershipHistory(
            member_id=member.id,
            plan_id=plan_id,
            start_date=join_date,
            end_date=expiry_date
        )

        db.session.add(history)
        inserted += 1

    db.session.commit()

    return jsonify({"inserted": inserted, "skipped": skipped})


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
