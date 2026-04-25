from app import app, db, Gym
from werkzeug.security import check_password_hash, generate_password_hash

EMAIL    = "your_gym_owner_email@gmail.com"  # <- replace
PASSWORD = "your_gym_password_here"          # <- replace

with app.app_context():
    gym = Gym.query.filter_by(email=EMAIL).first()

    if not gym:
        print("No account found. Listing all gym owners:\n")
        gyms = Gym.query.filter_by(role="gym").all()
        for g in gyms:
            print(f"  {g.email} | active={g.is_active} | deleted={g.is_deleted} | sub={g.subscription_expiry}")
    else:
        print(f"Found: {gym.email}")
        print(f"  role:                {gym.role}")
        print(f"  is_active:           {gym.is_active}")
        print(f"  is_deleted:          {gym.is_deleted}")
        print(f"  subscription_expiry: {gym.subscription_expiry}")

        pw_ok = check_password_hash(gym.password, PASSWORD)
        print(f"  password match:      {pw_ok}")

        if not pw_ok:
            gym.password = generate_password_hash(PASSWORD, method='pbkdf2:sha256', salt_length=16)
            db.session.commit()
            print("  Password has been reset. Try logging in again.")

        if gym.subscription_expiry:
            from datetime import datetime
            if gym.subscription_expiry < datetime.today().date():
                print("  BLOCKED: Subscription expired!")
                print("  Fix: update subscription_expiry in DB or run renew from admin panel.")
