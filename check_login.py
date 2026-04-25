from app import app, db, Gym, ADMIN_EMAILS
from werkzeug.security import check_password_hash

EMAIL    = ".env"   # your admin email
PASSWORD = ".env"             # your password

with app.app_context():
    print(f"\nADMIN_EMAILS from .env: {repr(ADMIN_EMAILS)}")

    gym = Gym.query.filter_by(email=EMAIL).first()
    if not gym:
        print("❌ Account not found")
    else:
        print(f"\nAccount found:")
        print(f"  email:      {gym.email}")
        print(f"  role:       {gym.role}")
        print(f"  is_active:  {gym.is_active}")
        print(f"  is_deleted: {gym.is_deleted}")

        pw_ok = check_password_hash(gym.password, PASSWORD)
        print(f"  password:   {'✅ matches' if pw_ok else '❌ WRONG'}")

        in_whitelist = gym.email in ADMIN_EMAILS
        print(f"  in whitelist: {'✅ yes' if in_whitelist else '❌ NO — this is blocking login!'}")

        print("\n── Login would fail because: ──")
        if not pw_ok:       print("  ❌ Password mismatch")
        if not in_whitelist: print("  ❌ Email not in ADMIN_EMAILS (.env)")
        if pw_ok and in_whitelist:
            print("  ✅ Nothing — login should work. Restart app.py and try again.")
