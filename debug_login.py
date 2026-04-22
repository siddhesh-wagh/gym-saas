from app import app, db, Gym
from werkzeug.security import check_password_hash, generate_password_hash

EMAIL    = "sid.website11@gmail.com"  # ← replace
PASSWORD = "Siddhesh@9321"          # ← replace

with app.app_context():
    gym = Gym.query.filter_by(email=EMAIL).first()

    if not gym:
        print("❌ No account found with that email")
    else:
        print(f"✅ Found account: {gym.email}")
        print(f"   Role:       {gym.role}")
        print(f"   is_active:  {gym.is_active}")
        print(f"   is_deleted: {gym.is_deleted}")
        print(f"   Hash start: {gym.password[:40]}...")

        match = check_password_hash(gym.password, PASSWORD)
        print(f"   Password match: {match}")

        if not match:
            print("\n⚠️  Password does not match — resetting now...")
            gym.password = generate_password_hash(PASSWORD, method='pbkdf2:sha256', salt_length=16)
            db.session.commit()
            print(f"✅ Password reset to: {PASSWORD}")
            print("   Try logging in again.")
