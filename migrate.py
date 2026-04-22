"""
Run this ONCE to migrate your database:
    python migrate.py

What it does:
  1. Adds is_active column to gym table (default True)
  2. Adds created_at column to gym table
  3. Adds is_deleted column to gym table (default False)
  4. Adds subscription_expiry column to gym table
  5. Adds is_active column to plan table (default True)
  6. Creates payment + audit_log tables
  7. Hashes any remaining plain-text passwords
"""

from app import app, db, Gym
from werkzeug.security import generate_password_hash


def run_sql(conn, sql, label):
    try:
        conn.execute(db.text(sql))
        conn.commit()
        print(f"  ✅ {label}")
    except Exception as e:
        conn.rollback()
        if "already exists" in str(e).lower():
            print(f"  ℹ️  {label} — already exists, skipping")
        else:
            print(f"  ❌ {label} FAILED: {e}")


with app.app_context():
    with db.engine.connect() as conn:

        print("\n── Gym table ──")
        run_sql(conn,
            "ALTER TABLE gym ADD COLUMN is_active BOOLEAN DEFAULT TRUE NOT NULL",
            "is_active column"
        )
        run_sql(conn,
            "ALTER TABLE gym ADD COLUMN created_at TIMESTAMP DEFAULT NOW()",
            "created_at column"
        )
        run_sql(conn,
            "ALTER TABLE gym ADD COLUMN is_deleted BOOLEAN DEFAULT FALSE NOT NULL",
            "is_deleted column"
        )
        run_sql(conn,
            "ALTER TABLE gym ADD COLUMN subscription_expiry DATE",
            "subscription_expiry column"
        )

        print("\n── Plan table ──")
        run_sql(conn,
            "ALTER TABLE plan ADD COLUMN is_active BOOLEAN DEFAULT TRUE NOT NULL",
            "is_active column"
        )

    # Create new tables (payment, audit_log) — safe to run multiple times
    db.create_all()
    print("\n  ✅ payment + audit_log tables ready")

    # Hash any remaining plain-text passwords
    print("\n── Passwords ──")
    gyms  = Gym.query.all()
    fixed = 0
    for gym in gyms:
        if not gym.password.startswith(("pbkdf2:", "scrypt:", "bcrypt:")):
            print(f"  ⚠️  Hashing plain-text password for: {gym.email}")
            gym.password = generate_password_hash(
                gym.password, method='pbkdf2:sha256', salt_length=16
            )
            fixed += 1

    if fixed:
        db.session.commit()
        print(f"  ✅ Hashed {fixed} plain-text password(s)")
    else:
        print("  ℹ️  All passwords already hashed")

    print("\n🎉 Migration complete! Run: python app.py")
    print("\n── To create your admin account, run this in a Python shell ──\n")
    print("  from app import app, db, Gym")
    print("  from werkzeug.security import generate_password_hash")
    print("  with app.app_context():")
    print("      admin = Gym(")
    print("          name='Super Admin',")
    print("          email='YOUR_EMAIL',")
    print("          password=generate_password_hash('YOUR_PASSWORD', method='pbkdf2:sha256', salt_length=16),")
    print("          role='admin'")
    print("      )")
    print("      db.session.add(admin)")
    print("      db.session.commit()")
    print("      print('Admin created!')")
