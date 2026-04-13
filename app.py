from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta

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
    return jsonify({"message": "Gym SaaS API running 🚀"})


# add members to gym
@app.route("/add-member", methods=["POST"])
def add_member():
    data = request.json

    name = data.get("name")
    phone = data.get("phone")
    plan_id = data.get("plan_id")
    gym_id = data.get("gym_id")

    # Get plan from DB
    plan = Plan.query.get(plan_id)

    if not plan:
        return jsonify({"error": "Invalid plan_id"}), 400

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


# -----------------------
# Create Tables
# -----------------------

with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(debug=True)
