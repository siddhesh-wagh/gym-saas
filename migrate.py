"""
Run this ONCE to migrate your database for this update:
    python migrate.py

What it does:
  1. Adds is_active column to gym table (default True)
  2. Adds created_at column to gym table
  3. Hashes any remaining plain-text passwords
"""

from app import app, db, Gym
from werkzeug.security import generate_password_hash


def run_sql(conn, sql, label):
    try:
        conn.execute(db.text(sql))
        conn.commit()
        print(f"✅ {label}")
    except Exception as e:
        conn.rollback()
        if "already exists" in str(e).lower():
            print(f"ℹ️  {label} — already exists, skipping")
        else:
            print(f"❌ {label} FAILED: {e}")


with app.app_context():
    with db.engine.connect() as conn:

        run_sql(conn,
            "ALTER TABLE gym ADD COLUMN is_active BOOLEAN DEFAULT TRUE NOT NULL",
            "Added is_active column"
        )

        run_sql(conn,
            "ALTER TABLE gym ADD COLUMN created_at TIMESTAMP DEFAULT NOW()",
            "Added created_at column"
        )

    # Hash any remaining plain-text passwords
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
        print(f"✅ Hashed {fixed} plain-text password(s)")
    else:
        print("ℹ️  All passwords already hashed")

    print("\n🎉 Migration complete!")
    print("\n── Next step: create your admin account ──")
    print("Run this in a Python shell:\n")
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
