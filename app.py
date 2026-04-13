from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from flask import render_template

import csv


app = Flask(__name__)

# PostgreSQL connection
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

@app.route("/")
def home():
    return render_template("index.html")



# add members to gym
@app.route("/add-member", methods=["POST"])
def add_member():
    data = request.form  # ✅ FIXED

    name = data.get("name")
    phone = data.get("phone")
    plan_id = data.get("plan_id")
    gym_id = data.get("gym_id")

    plan = Plan.query.get(plan_id)

    if not plan:
        return "Invalid plan_id"

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

    return f"Member added! Expiry: {expiry_date}"


# singup
@app.route("/signup", methods=["POST"])
def signup():
    data = request.json

    name = data.get("name")
    email = data.get("email")
    password = data.get("password")

    # Check if gym already exists
    existing_gym = Gym.query.filter_by(email=email).first()

    if existing_gym:
        return jsonify({"error": "Gym already exists"}), 400

    new_gym = Gym(
        name=name,
        email=email,
        password=password
    )

    db.session.add(new_gym)
    db.session.commit()

    return jsonify({
        "message": "Gym created successfully",
        "gym_id": new_gym.id
    })

# login
@app.route("/login", methods=["POST"])
def login():
    data = request.json

    email = data.get("email")
    password = data.get("password")

    gym = Gym.query.filter_by(email=email, password=password).first()

    if not gym:
        return jsonify({"error": "Invalid email or password"}), 401

    return jsonify({
        "message": "Login successful",
        "gym_id": gym.id
    })

# all members
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

# expiring
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
            "id": m.id,
            "name": m.name,
            "phone": m.phone,
            "expiry_date": str(m.expiry_date)
        })

    return jsonify(result)

# CSV upload (bulk insert optimized)
@app.route("/upload-csv", methods=["POST"])
def upload_csv():
    # Get file + form data
    file = request.files.get("file")
    gym_id = request.form.get("gym_id")
    plan_id = request.form.get("plan_id")

    # Convert to int (IMPORTANT)
    gym_id = int(gym_id)
    plan_id = int(plan_id)

    # Check file
    if not file:
        return jsonify({"error": "No file uploaded"}), 400

    # Get plan from DB
    plan = Plan.query.get(plan_id)

    if not plan:
        return jsonify({"error": "Invalid plan_id"}), 400

    # Calculate dates
    join_date = datetime.today().date()
    expiry_date = join_date + timedelta(days=plan.duration_days)

    # Read CSV file
    csv_data = file.read().decode("utf-8").splitlines()
    reader = csv.DictReader(csv_data)

    # Prepare bulk list
    members_list = []

    for row in reader:
        name = row.get("name")
        phone = row.get("phone")

        member = Member(
            name=name,
            phone=phone,
            join_date=join_date,
            expiry_date=expiry_date,
            gym_id=gym_id,
            plan_id=plan_id
        )

        members_list.append(member)

    # Bulk insert (FAST 🚀)
    db.session.bulk_save_objects(members_list)
    db.session.commit()

    return jsonify({
        "message": f"{len(members_list)} members uploaded successfully"
    })

# expiry alert
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


if __name__ == "__main__":
    app.run(debug=True)
