from app import app, db, Gym
from werkzeug.security import generate_password_hash

EMAIL       = "siddhesh.01092004@gmail.com"
NEW_PASSWORD = "Sid@123#"   # <- set whatever password you want

with app.app_context():
    gym = Gym.query.filter_by(email=EMAIL).first()

    if not gym:
        print("Account not found")
    else:
        gym.is_deleted = False
        gym.is_active  = True
        gym.password   = generate_password_hash(NEW_PASSWORD, method='pbkdf2:sha256', salt_length=16)
        db.session.commit()
        print(f"Fixed: {gym.email}")
        print(f"  is_deleted: {gym.is_deleted}")
        print(f"  is_active:  {gym.is_active}")
        print(f"  password reset to: {NEW_PASSWORD}")
        print("Login should work now.")
