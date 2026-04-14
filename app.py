from flask import Flask, jsonify, request, render_template
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import csv
import os
import random

app = Flask(__name__)

# -----------------------
# Config
# -----------------------

UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# Create folder if not exists ✅
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://gym_admin:gym123@localhost:5432/gym_saas'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# -----------------------
# Models
# -----------------------

class Gym(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))


class Plan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50))
    duration_days = db.Column(db.Integer)


def generate_member_id():
    return str(random.randint(100, 999))


class Member(db.Model):
    __table_args__ = (
        db.UniqueConstraint('phone', 'gym_id', name='unique_member_per_gym'),
    )

    id = db.Column(db.Integer, primary_key=True)
    unique_id = db.Column(db.String(10), unique=True)

    name = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))

    age = db.Column(db.Integer)
    gender = db.Column(db.String(10))
    address = db.Column(db.String(200))
    photo = db.Column(db.String(200))

    join_date = db.Column(db.Date)
    expiry_date = db.Column(db.Date)

    gym_id = db.Column(db.Integer, db.ForeignKey('gym.id'))
    plan_id = db.Column(db.Integer, db.ForeignKey('plan.id'))

# -----------------------
# Routes
# -----------------------

@app.route("/")
def home():
    return render_template("index.html")


# -----------------------
# Add Member
# -----------------------
@app.route("/add-member", methods=["POST"])
def add_member():
    try:
        name = request.form.get("name")
        phone = request.form.get("phone")
        email = request.form.get("email")
        age = request.form.get("age")
        gender = request.form.get("gender")
        address = request.form.get("address")

        gym_id = int(request.form.get("gym_id"))
        plan_id = int(request.form.get("plan_id"))

        file = request.files.get("photo")

        # Validation
        if not name or not phone:
            return jsonify({"error": "Name and phone required"}), 400

        # Duplicate check
        existing = Member.query.filter_by(phone=phone, gym_id=gym_id).first()
        if existing:
            return jsonify({"error": "Member already exists"}), 400

        # Plan check
        plan = db.session.get(Plan, plan_id)
        if not plan:
            return jsonify({"error": "Invalid plan"}), 400

        # Save photo
        photo_path = None
        if file and file.filename != "":
            filename = f"{phone}.jpg"
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file.save(filepath)
            photo_path = "/" + filepath.replace("\\", "/")

        # Dates
        join_date = datetime.today().date()
        expiry_date = join_date + timedelta(days=plan.duration_days)

        # Unique ID (retry if duplicate)
        while True:
            unique_id = generate_member_id()
            exists = Member.query.filter_by(unique_id=unique_id).first()
            if not exists:
                break

        # Create member
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
        db.session.commit()

        return jsonify({
            "message": "Member added successfully",
            "member_id": unique_id,
            "expiry_date": str(expiry_date)
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# -----------------------
# Get Members
# -----------------------
@app.route("/members/<int:gym_id>", methods=["GET"])
def get_members(gym_id):
    members = Member.query.filter_by(gym_id=gym_id).all()

    result = []
    for m in members:
        result.append({
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
# Expiry Alerts
# -----------------------
@app.route("/expiry-alerts/<int:gym_id>", methods=["GET"])
def expiry_alerts(gym_id):
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
    file = request.files.get("file")
    gym_id = request.form.get("gym_id")
    plan_id = request.form.get("plan_id")

    if not file:
        return jsonify({"error": "No file uploaded"}), 400

    gym_id = int(gym_id)
    plan_id = int(plan_id)

    plan = db.session.get(Plan, plan_id)
    if not plan:
        return jsonify({"error": "Invalid plan"}), 400

    join_date = datetime.today().date()
    expiry_date = join_date + timedelta(days=plan.duration_days)

    csv_data = file.read().decode("utf-8").splitlines()
    reader = csv.DictReader(csv_data)

    inserted = 0
    skipped = 0

    for row in reader:
        name = row.get("name")
        phone = row.get("phone")

        if not name or not phone:
            skipped += 1
            continue

        existing = Member.query.filter_by(phone=phone, gym_id=gym_id).first()
        if existing:
            skipped += 1
            continue

        member = Member(
            name=name,
            phone=phone,
            join_date=join_date,
            expiry_date=expiry_date,
            gym_id=gym_id,
            plan_id=plan_id
        )

        db.session.add(member)
        inserted += 1

    db.session.commit()

    return jsonify({
        "inserted": inserted,
        "skipped": skipped
    })


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
