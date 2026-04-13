from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

# PostgreSQL connection
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://gym_admin:gym123@localhost:5432/gym_saas'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

@app.route("/")
def home():
    return jsonify({"message": "Connected to PostgreSQL successfully 🚀"})

if __name__ == "__main__":
    app.run(debug=True)
