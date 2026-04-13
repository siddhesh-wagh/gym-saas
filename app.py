from flask import Flask, jsonify, request, render_template
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import csv

app = Flask(__name__)

# -----------------------
# Database Config
# -----------------------
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://gym_admin:gym123@localhost:5432/gym_saas'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# -----------------------
# Models (Tables)
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


class Member(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    phone = db.Column(db.String(20))

    join_date = db.Column(db.Date)
    expiry_date = db.Column(db.Date)

    gym_id = db.Column(db.Integer, db.ForeignKey('gym.id'))
    plan_id = db.Column(db.Integer, db.ForeignKey('plan.id'))

# -----------------------
# Routes
# -----------------------

# Home (Frontend Page)
@app.route("/")
def home():
    return render_template("index.html")


# -----------------------
# Add Member API
# -----------------------
@app.route("/add-member", methods=["POST"])
def add_member():
    data = request.get_json()

    name = data.get("name")
    phone = data.get("phone")
    plan_id = int(data.get("plan_id"))
    gym_id = int(data.get("gym_id"))

    # Get plan
    plan = db.session.get(Plan, plan_id)  # ✅ modern method

    if not plan:
        return jsonify({"error": "Invalid plan_id"}), 400

    # Date logic
    join_date = datetime.today().date()
    expiry_date = join_date + timedelta(days=plan.duration_days)

    new_member = Member(
        name=name,
        phone=phone,
        join_date=join_date,
        expiry_date=expiry_date,
        gym_id=gym_id,
        plan_id=plan_id
    )

    db.session.add(new_member)
    db.session.commit()

    return jsonify({
        "message": "Member added successfully",
        "expiry_date": str(expiry_date)
    })


# -----------------------
# Signup API
# -----------------------
@app.route("/signup", methods=["POST"])
def signup():
    data = request.get_json()

    name = data.get("name")
    email = data.get("email")
    password = data.get("password")

    # Check existing
    existing = Gym.query.filter_by(email=email).first()

    if existing:
        return jsonify({"error": "Gym already exists"}), 400

    new_gym = Gym(name=name, email=email, password=password)

    db.session.add(new_gym)
    db.session.commit()

    return jsonify({
        "message": "Gym created successfully",
        "gym_id": new_gym.id
    })


# -----------------------
# Login API
# -----------------------
@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()

    email = data.get("email")
    password = data.get("password")

    gym = Gym.query.filter_by(email=email, password=password).first()

    if not gym:
        return jsonify({"error": "Invalid credentials"}), 401

    return jsonify({
        "message": "Login successful",
        "gym_id": gym.id
    })


# -----------------------
# Get All Members
# -----------------------
@app.route("/members/<int:gym_id>", methods=["GET"])
def get_members(gym_id):
    members = Member.query.filter_by(gym_id=gym_id).all()

    result = []
    for m in members:
        result.append({
            "id": m.id,
            "name": m.name,
            "phone": m.phone,
            "join_date": str(m.join_date),
            "expiry_date": str(m.expiry_date)
        })

    return jsonify(result)


# -----------------------
# Expiring Members (Next 3 Days)
# -----------------------
@app.route("/expiring-members/<int:gym_id>", methods=["GET"])
def get_expiring_members(gym_id):
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
# CSV Upload (Bulk Insert with Duplicate Check)
# -----------------------
@app.route("/upload-csv", methods=["POST"])
def upload_csv():
    file = request.files.get("file")
    gym_id = request.form.get("gym_id")
    plan_id = request.form.get("plan_id")

    # Validate input
    if not file:
        return jsonify({"error": "No file uploaded"}), 400

    if not gym_id or not plan_id:
        return jsonify({"error": "gym_id and plan_id required"}), 400

    # Convert to int
    gym_id = int(gym_id)
    plan_id = int(plan_id)

    # Get plan
    plan = db.session.get(Plan, plan_id)
    if not plan:
        return jsonify({"error": "Invalid plan_id"}), 400

    # Dates
    join_date = datetime.today().date()
    expiry_date = join_date + timedelta(days=plan.duration_days)

    # Read CSV
    csv_data = file.read().decode("utf-8").splitlines()
    reader = csv.DictReader(csv_data)

    inserted = 0
    skipped = 0

    for row in reader:
        name = row.get("name")
        phone = row.get("phone")

        # Skip empty rows
        if not name or not phone:
            skipped += 1
            continue

        # 🔥 Check duplicate phone inside same gym
        existing_member = Member.query.filter_by(
            phone=phone,
            gym_id=gym_id
        ).first()

        if existing_member:
            skipped += 1
            continue

        # Create member
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
        "message": "CSV upload completed",
        "inserted": inserted,
        "skipped_duplicates": skipped
    })



# -----------------------
# Expiry Alerts API
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
# Create Tables
# -----------------------
with app.app_context():
    db.create_all()


# -----------------------
# Run App
# -----------------------
if __name__ == "__main__":
    app.run(debug=True)
