# import requests

# url = "http://127.0.0.1:5000/upload-csv"

# files = {
#     'file': open('members.csv', 'rb')
# }

# data = {
#     'gym_id': 1,
#     'plan_id': 1
# }

# response = requests.post(url, files=files, data=data)

# print("Status:", response.status_code)
# print("Response:", response.text)

from app import app, db, Member, Gym
import re

def normalize_phone(phone):
    if not phone: return phone
    phone = re.sub(r'[\s\-\(\)]', '', phone)
    phone = re.sub(r'^\+91', '', phone)
    phone = re.sub(r'^91(\d{10})$', r'\1', phone)
    return phone.strip()

with app.app_context():
    fixed = 0
    skipped = 0
    deleted = 0

    for m in Member.query.all():
        clean = normalize_phone(m.phone)
        if clean == m.phone:
            continue  # already clean, skip

        # Check if another member in same gym already has this clean number
        conflict = Member.query.filter_by(phone=clean, gym_id=m.gym_id).first()
        if conflict and conflict.id != m.id:
            # Duplicate — delete the dirty one, keep the clean one
            print(f"  Duplicate found: '{m.phone}' conflicts with '{clean}' in gym {m.gym_id} — deleting member id {m.id} ({m.name})")
            db.session.delete(m)
            deleted += 1
        else:
            m.phone = clean
            fixed += 1

    db.session.commit()

    # Now fix Gym phones
    for g in Gym.query.all():
        if not g.phone: continue
        clean = normalize_phone(g.phone)
        if clean != g.phone:
            g.phone = clean
            fixed += 1

    db.session.commit()
    print(f"\n✅ Fixed: {fixed} | Deleted duplicates: {deleted} | Skipped: {skipped}")