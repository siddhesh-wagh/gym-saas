from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import date

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
    return jsonify({"message": "Tables ready 🚀"})


# -----------------------
# Create Tables
# -----------------------

with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(debug=True)
