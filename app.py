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
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config['SQLALCHEMY_DATABASE_URI'] = \
'postgresql://gym_admin:gym123@localhost:5432/gym_saas'

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
    return str(random.randint(1000, 9999))  # safer than 3 digit


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

    # relationship
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

        # Duplicate checks
        if Member.query.filter_by(phone=phone, gym_id=gym_id).first():
            return jsonify({"error": "Phone already exists"}), 400

        if email and Member.query.filter_by(email=email, gym_id=gym_id).first():
            return jsonify({"error": "Email already exists"}), 400

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

        # Unique ID
        while True:
            unique_id = generate_member_id()
            if not Member.query.filter_by(unique_id=unique_id).first():
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
        db.session.flush()

        # Save history
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
        return jsonify({"error": str(e)}), 500


# -----------------------
# Renew Membership
# -----------------------
@app.route("/renew-member", methods=["POST"])
def renew_member():
    data = request.get_json()

    member_id = data.get("member_id")
    plan_id = data.get("plan_id")

    member = Member.query.get(member_id)
    plan = Plan.query.get(plan_id)

    if not member or not plan:
        return jsonify({"error": "Invalid member or plan"}), 400

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
    member = Member.query.filter_by(unique_id=unique_id).first()

    if not member:
        return "Member not found", 404

    return render_template("member.html", member=member)


# -----------------------
# Get Members
# -----------------------
@app.route("/members/<int:gym_id>")
def get_members(gym_id):
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
    member = db.session.get(Member, id)

    if not member:
        return jsonify({"error": "Member not found"}), 404

    db.session.delete(member)
    db.session.commit()

    return jsonify({"message": "Member deleted"})

# -----------------------
# Update Member
# -----------------------
@app.route("/update-member/<int:id>", methods=["PUT"])
def update_member(id):
    member = db.session.get(Member, id)

    if not member:
        return jsonify({"error": "Member not found"}), 404

    data = request.get_json()

    member.name = data.get("name", member.name)
    member.phone = data.get("phone", member.phone)
    member.email = data.get("email", member.email)

    # ✅ FIX: safe integer handling
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
# CSV Upload (FIXED)
# -----------------------
@app.route("/upload-csv", methods=["POST"])
def upload_csv():
    file = request.files.get("file")
    gym_id = int(request.form.get("gym_id"))
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

        # duplicate checks
        if Member.query.filter_by(phone=phone, gym_id=gym_id).first() or \
           (email and Member.query.filter_by(email=email, gym_id=gym_id).first()):
            skipped += 1
            continue

        # unique ID
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
