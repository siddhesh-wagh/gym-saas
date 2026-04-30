"""
Run ONCE: python migrate.py

What it does:
  1. Adds phone, approval_status columns to gym table
  2. Adds price, gym_id columns to plan table
  3. Adds amount_paid to membership_history table
  4. Sets all existing gyms to approved (so they don't get locked out)
  5. Hashes any remaining plain-text passwords
  6. Creates new tables (activity_log, payment) if not exist
"""

from app import app, db, Gym, Plan, MembershipHistory
from werkzeug.security import generate_password_hash


def run(conn, sql, label):
    try:
        conn.execute(db.text(sql))
        conn.commit()
        print(f"  ✅ {label}")
    except Exception as e:
        conn.rollback()
        if "already exists" in str(e).lower():
            print(f"  ℹ️  {label} — already exists, skipped")
        else:
            print(f"  ❌ {label}: {e}")


with app.app_context():

    with db.engine.connect() as conn:
         Delete old global plans (gym_id is NULL)
        conn.execute(db.text("DELETE FROM plan WHERE gym_id IS NULL"))
        # Reset sequence
        conn.execute(db.text(
            "SELECT setval('plan_id_seq', COALESCE((SELECT MAX(id) FROM plan), 1))"
        ))
        conn.commit()
        print("✅ Old global plans removed, sequence reset")
        
        print("\n── Gym table ──")
        run(conn,
            "ALTER TABLE gym ADD COLUMN phone VARCHAR(20)",
            "phone column")
        run(conn,
            "ALTER TABLE gym ADD COLUMN approval_status VARCHAR(20) DEFAULT 'approved'",
            "approval_status column")
        run(conn,
            "ALTER TABLE gym ADD COLUMN is_deleted BOOLEAN DEFAULT FALSE NOT NULL",
            "is_deleted column")
        run(conn,
            "ALTER TABLE gym ADD COLUMN is_active BOOLEAN DEFAULT TRUE NOT NULL",
            "is_active column")
        run(conn,
            "ALTER TABLE gym ADD COLUMN created_at TIMESTAMP DEFAULT NOW()",
            "created_at column")
        run(conn,
            "ALTER TABLE gym ADD COLUMN subscription_expiry DATE",
            "subscription_expiry column")

        print("\n── Plan table ──")
        run(conn,
            "ALTER TABLE plan ADD COLUMN price INTEGER DEFAULT 0",
            "price column")
        run(conn,
            "ALTER TABLE plan ADD COLUMN gym_id INTEGER REFERENCES gym(id)",
            "gym_id column")
        run(conn,
            "ALTER TABLE plan ADD COLUMN is_active BOOLEAN DEFAULT TRUE NOT NULL",
            "is_active column")

        print("\n── MembershipHistory table ──")
        run(conn,
            "ALTER TABLE membership_history ADD COLUMN amount_paid INTEGER DEFAULT 0",
            "amount_paid column")

        print("\n── Set existing gyms to approved ──")
        run(conn,
            "UPDATE gym SET approval_status = 'approved', is_active = TRUE WHERE role = 'gym'",
            "Existing gyms approved")

    # Create any missing tables (activity_log, payment, etc.)
    db.create_all()
    print("\n  ✅ New tables created (if not exist)")

    # Hash plain-text passwords
    print("\n── Passwords ──")
    fixed = 0
    for gym in Gym.query.all():
        if not gym.password.startswith(("pbkdf2:", "scrypt:", "bcrypt:")):
            print(f"  ⚠️  Hashing password for: {gym.email}")
            gym.password = generate_password_hash(
                gym.password, method='pbkdf2:sha256', salt_length=16
            )
            fixed += 1
    if fixed:
        db.session.commit()
        print(f"  ✅ Hashed {fixed} password(s)")
    else:
        print("  ℹ️  All passwords already hashed")

    print("\n🎉 Migration complete — run: python app.py")
    print("\n── To set up Fast2SMS (optional) ──")
    print("  Add to your .env file:")
    print("  FAST2SMS_API_KEY=your_key_from_fast2sms.com")
    print("\n── To set ADMIN_EMAILS ──")
    print("  Add to your .env file:")
    print("  ADMIN_EMAILS=your@email.com")
