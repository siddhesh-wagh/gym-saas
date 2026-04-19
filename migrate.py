"""
Run this ONCE to migrate your existing database:
  python migrate.py

It will:
  1. Add the 'role' column to the gym table
  2. Set all existing gyms to role = 'gym'
"""

from app import app, db
from werkzeug.security import generate_password_hash

with app.app_context():
    with db.engine.connect() as conn:

        # Step 1: Add role column
        try:
            conn.execute(db.text(
                "ALTER TABLE gym ADD COLUMN role VARCHAR(20) DEFAULT 'gym' NOT NULL"
            ))
            conn.commit()
            print("✅ Column 'role' added successfully.")
        except Exception as e:
            conn.rollback()
            if "already exists" in str(e).lower():
                print("ℹ️  Column 'role' already exists, skipping.")
            else:
                print(f"❌ Error adding column: {e}")

        # Step 2: Set all existing gyms to role = 'gym'
        try:
            conn.execute(db.text("UPDATE gym SET role = 'gym' WHERE role IS NULL"))
            conn.commit()
            print("✅ All existing gyms set to role = 'gym'.")
        except Exception as e:
            conn.rollback()
            print(f"❌ Error updating roles: {e}")

    # Step 3: Fix plain-text passwords (hash them)
    from app import Gym
    gyms = Gym.query.all()
    fixed = 0
    for gym in gyms:
        # Werkzeug hashes start with 'pbkdf2:', 'scrypt:', or 'bcrypt:'
        if not gym.password.startswith(("pbkdf2:", "scrypt:", "bcrypt:")):
            print(f"⚠️  Hashing plain-text password for: {gym.email}")
            gym.password = generate_password_hash(gym.password)
            fixed += 1

    if fixed > 0:
        db.session.commit()
        print(f"✅ Hashed {fixed} plain-text password(s).")
    else:
        print("ℹ️  All passwords already hashed, skipping.")

    print("\n🎉 Migration complete! You can now run: python app.py")