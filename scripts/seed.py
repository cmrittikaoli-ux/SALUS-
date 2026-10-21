"""Populate the SALUS database with realistic dummy data (Mumbai-based).

All dates are relative to *now*, so re-running always gives you past
history plus upcoming appointments. Output is deterministic for a given
--seed and run date.

    python scripts/seed.py                 # uses DATABASE_URL or the default below
    python scripts/seed.py --reset         # wipe existing data first

Future appointments are booked through fn_book_appointment() — the same
path the API uses — so the booking rules and reminder triggers run for real.
"""
from __future__ import annotations

import argparse
import os
import random
import sys
import uuid
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg
from psycopg.types.range import Range

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.config import DEMO_PASSWORD  # noqa: E402
from app.diet_rules import check_meal  # noqa: E402

TZ = ZoneInfo("Asia/Kolkata")
DEFAULT_URL = "postgresql://postgres:postgres@localhost:5432/salus"

# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------
SPECIALTIES = {
    # name: (fee range INR, slot minutes, number of doctors)
    "General Physician": ((300, 800), 15, 9),
    "Cardiologist": ((1000, 2500), 30, 6),
    "Dermatologist": ((600, 1500), 20, 6),
    "Orthopedic": ((800, 1800), 20, 6),
    "Pediatrician": ((500, 1200), 15, 6),
    "Gynecologist": ((700, 1800), 20, 5),
    "ENT Specialist": ((500, 1200), 15, 4),
    "Ophthalmologist": ((500, 1500), 20, 4),
    "Neurologist": ((1200, 2500), 30, 4),
    "Psychiatrist": ((1000, 2500), 45, 4),
    "Gastroenterologist": ((1000, 2200), 30, 4),
    "Endocrinologist": ((900, 2000), 30, 4),
    "Pulmonologist": ((800, 1800), 30, 3),
    "Urologist": ((800, 1800), 20, 3),
    "Dentist": ((300, 1000), 30, 6),
}

# Mumbai neighbourhoods with approximate centre coordinates (lat, lon)
AREAS = [
    ("Colaba", 18.9067, 72.8147, "400005"), ("Churchgate", 18.9322, 72.8264, "400020"),
    ("Grant Road", 18.9633, 72.8156, "400007"), ("Byculla", 18.9790, 72.8330, "400027"),
    ("Lower Parel", 18.9953, 72.8258, "400013"), ("Worli", 19.0176, 72.8174, "400018"),
    ("Dadar", 19.0178, 72.8478, "400014"), ("Matunga", 19.0270, 72.8570, "400019"),
    ("Sion", 19.0400, 72.8620, "400022"), ("Bandra West", 19.0596, 72.8295, "400050"),
    ("Khar", 19.0700, 72.8370, "400052"), ("Santacruz", 19.0810, 72.8410, "400054"),
    ("Vile Parle", 19.1000, 72.8440, "400057"), ("Juhu", 19.1075, 72.8263, "400049"),
    ("Andheri West", 19.1363, 72.8277, "400053"), ("Andheri East", 19.1136, 72.8697, "400069"),
    ("Goregaon", 19.1646, 72.8493, "400063"), ("Malad", 19.1870, 72.8480, "400064"),
    ("Borivali", 19.2307, 72.8567, "400092"), ("Kurla", 19.0726, 72.8845, "400070"),
    ("Chembur", 19.0522, 72.9005, "400071"), ("Ghatkopar", 19.0860, 72.9081, "400077"),
    ("Powai", 19.1176, 72.9060, "400076"), ("Mulund", 19.1726, 72.9425, "400080"),
    ("Thane", 19.2183, 72.9781, "400601"), ("Vashi", 19.0771, 72.9986, "400703"),
]
STREETS = ["S.V. Road", "L.B.S. Marg", "Linking Road", "Hill Road", "M.G. Road", "Station Road",
           "Carter Road", "J.P. Road", "Tilak Road", "Ghodbunder Road", "Sector 17", "Hiranandani Gardens",
           "Nehru Road", "Ranade Road", "Senapati Bapat Marg", "Dr. Ambedkar Road", "Sion Trombay Road"]
BUILDINGS = ["Sai Krupa", "Shanti Niketan", "Om Heights", "Ganga Towers", "Lotus Plaza", "Kalpataru",
             "Sunrise Complex", "Arihant Arcade", "Galaxy Point", "Shivam Chambers", "Neelkanth", "Vishal Tower"]

FIRST_F = ["Aarti", "Ananya", "Priya", "Sneha", "Pooja", "Neha", "Kavya", "Isha", "Riya", "Meera", "Shruti",
           "Anjali", "Divya", "Swati", "Nandini", "Tanvi", "Ritika", "Aditi", "Sanjana", "Mrunal", "Pallavi",
           "Madhuri", "Farah", "Zoya", "Sayali", "Rashmi", "Ishita", "Trisha", "Payal", "Gauri", "Fatima",
           "Roshni", "Jyoti", "Lakshmi", "Deepika", "Radhika", "Mansi", "Ketaki", "Bhavna", "Shalini"]
FIRST_M = ["Aarav", "Rohan", "Arjun", "Vikram", "Rahul", "Amit", "Siddharth", "Karan", "Nikhil", "Aditya",
           "Varun", "Pranav", "Harsh", "Omkar", "Sahil", "Yash", "Manish", "Suresh", "Rajesh", "Imran",
           "Farhan", "Kunal", "Tejas", "Akshay", "Sameer", "Gaurav", "Ashwin", "Devendra", "Mihir",
           "Parth", "Ravi", "Sanjay", "Abhishek", "Chirag", "Nilesh", "Vivek", "Ajay", "Anil", "Hemant", "Irfan"]
LAST = ["Sharma", "Patil", "Deshmukh", "Kulkarni", "Joshi", "Iyer", "Nair", "Menon", "Reddy", "Shah",
        "Mehta", "Desai", "Gupta", "Chatterjee", "Banerjee", "Mukherjee", "Das", "Sawant", "Pawar", "Jadhav",
        "Shinde", "Gokhale", "Rao", "Pillai", "Khan", "Shaikh", "Fernandes", "D'Souza", "Kapoor", "Malhotra",
        "Agarwal", "Bhatt", "Trivedi", "Chavan", "More", "Naik", "Kamat", "Sen", "Bose", "Verma", "Singh",
        "Tiwari", "Pandey", "Mishra", "Gadgil", "Bhosale", "Rane", "Ghosh", "Parekh", "Thakkar"]

DIET_NOTES = ["Vegetarian", "Vegetarian", "Jain - no onion, garlic or root vegetables", "Eggetarian",
              "Vegan", "Lactose intolerant", "Gluten-free", "Diabetic - low sugar diet",
              "Low sodium diet", "Nut allergy (peanuts, cashews)", "Vegetarian, lactose intolerant",
              "Low sugar, low sodium"]

# drug, dosage text, times per day (list of HH:MM), days_of_week or None, chronic?
DRUGS = [
    ("Metformin 500mg", "1 tablet twice daily after meals", ["08:30", "20:30"], None, True),
    ("Amlodipine 5mg", "1 tablet once daily", ["09:00"], None, True),
    ("Atorvastatin 10mg", "1 tablet at bedtime", ["22:00"], None, True),
    ("Telmisartan 40mg", "1 tablet once daily", ["08:00"], None, True),
    ("Levothyroxine 50mcg", "1 tablet on empty stomach", ["07:00"], None, True),
    ("Pantoprazole 40mg", "1 tablet before breakfast", ["07:30"], None, False),
    ("Omeprazole 20mg", "1 capsule before breakfast", ["07:30"], None, False),
    ("Montelukast 10mg", "1 tablet at night", ["21:30"], None, False),
    ("Cetirizine 10mg", "1 tablet at night", ["21:00"], None, False),
    ("Azithromycin 500mg", "1 tablet once daily for 5 days", ["10:00"], None, False),
    ("Amoxicillin 500mg", "1 capsule three times daily", ["08:00", "14:00", "20:00"], None, False),
    ("Paracetamol 650mg", "1 tablet up to three times daily", ["09:00", "15:00", "21:00"], None, False),
    ("Ibuprofen 400mg", "1 tablet twice daily after food", ["09:00", "21:00"], None, False),
    ("Vitamin D3 60000 IU", "1 sachet once a week", ["09:00"], [0], True),
    ("Calcium + Vitamin D3", "1 tablet daily after lunch", ["14:00"], None, True),
    ("Ferrous Ascorbate 100mg", "1 tablet daily", ["13:30"], None, False),
    ("Methylcobalamin 1500mcg", "1 tablet Mon/Wed/Fri", ["09:00"], [1, 3, 5], False),
    ("Escitalopram 10mg", "1 tablet once daily", ["09:00"], None, True),
    ("Glimepiride 1mg", "1 tablet before breakfast", ["08:00"], None, True),
    ("Salbutamol inhaler", "2 puffs twice daily", ["08:00", "20:00"], None, True),
]

# (meal_type, description, calories). Descriptions name their ingredients so
# the dietary-notes check can work on them.
MEALS = [
    ("breakfast", "Poha with peanuts and lemon", 320), ("breakfast", "Rava upma with vegetables", 290),
    ("breakfast", "Idli with sambar and coconut chutney", 300), ("breakfast", "Masala dosa with sambar", 410),
    ("breakfast", "Aloo paratha with curd", 480), ("breakfast", "Vegetable omelette with bread", 360),
    ("breakfast", "Besan chilla with mint chutney", 280), ("breakfast", "Moong dal chilla", 260),
    ("breakfast", "Oats porridge with milk and banana", 310), ("breakfast", "Sabudana khichdi", 380),
    ("breakfast", "Ragi dosa with tomato chutney", 270), ("breakfast", "Boiled eggs and toast", 300),
    ("breakfast", "Fruit bowl with papaya and apple", 180), ("breakfast", "Methi thepla with pickle", 350),
    ("lunch", "Dal tadka, jeera rice and salad", 520), ("lunch", "Rajma chawal with salad", 560),
    ("lunch", "Chapati, bhindi sabzi and dal", 500), ("lunch", "Chicken curry with rice", 650),
    ("lunch", "Paneer butter masala with naan", 720), ("lunch", "Vegetable pulao with raita", 540),
    ("lunch", "Fish curry with rice (surmai)", 610), ("lunch", "Chole with jeera rice", 590),
    ("lunch", "Curd rice with pomegranate", 420), ("lunch", "Moong dal khichdi with kadhi", 480),
    ("lunch", "Brown rice, lauki sabzi and dal", 470), ("lunch", "Quinoa pulao with vegetables", 450),
    ("lunch", "Sambar rice with cabbage poriyal", 490), ("lunch", "Egg curry with chapati", 560),
    ("dinner", "Chapati with mixed vegetable sabzi", 430), ("dinner", "Moong dal khichdi", 380),
    ("dinner", "Grilled chicken with sauteed vegetables", 460), ("dinner", "Palak paneer with roti", 520),
    ("dinner", "Vegetable soup and multigrain bread", 320), ("dinner", "Jowar bhakri with pithla", 450),
    ("dinner", "Dal and rice with papad", 470), ("dinner", "Tofu stir fry with rice", 430),
    ("dinner", "Masoor dal with jeera rice", 460), ("dinner", "Mutton keema with pav", 690),
    ("dinner", "Lauki chana dal with rice", 440), ("dinner", "Tomato rasam with rice", 380),
    ("snack", "Roasted makhana", 120), ("snack", "Sprouts chaat", 150), ("snack", "Masala chaas (buttermilk)", 70),
    ("snack", "Apple and almonds", 190), ("snack", "Dhokla", 160), ("snack", "Coconut water", 60),
    ("snack", "Cucumber and carrot sticks", 50), ("snack", "Gulab jamun", 300), ("snack", "Banana", 105),
    ("snack", "Roasted chana", 140), ("snack", "Mango shake", 280), ("snack", "Vada pav", 290),
]

# specialty: (postgraduate degrees, services offered)
PROFILE = {
    "General Physician": (["MD (General Medicine)", "DNB (Family Medicine)"],
                          ["Fever and infections", "Diabetes follow-up", "Blood pressure checks", "Health check-ups"]),
    "Cardiologist": (["MD (Medicine), DM (Cardiology)", "DNB (Cardiology)"],
                     ["ECG and echo review", "Hypertension", "Chest pain evaluation", "Post-angioplasty care"]),
    "Dermatologist": (["MD (Dermatology)", "DVD"], ["Acne and scars", "Eczema and psoriasis", "Hair loss", "Skin allergies"]),
    "Orthopedic": (["MS (Orthopaedics)", "DNB (Orthopaedics)"],
                   ["Knee and back pain", "Sports injuries", "Fracture care", "Arthritis"]),
    "Pediatrician": (["MD (Paediatrics)", "DCH"], ["Vaccinations", "Growth monitoring", "Newborn care", "Childhood asthma"]),
    "Gynecologist": (["MS (Obstetrics & Gynaecology)", "DGO"],
                     ["Antenatal care", "PCOS", "Menstrual problems", "Menopause care"]),
    "ENT Specialist": (["MS (ENT)", "DLO"], ["Sinusitis", "Hearing tests", "Tonsils", "Vertigo"]),
    "Ophthalmologist": (["MS (Ophthalmology)", "DO"], ["Eye check-ups", "Cataract assessment", "Glaucoma", "Dry eyes"]),
    "Neurologist": (["MD (Medicine), DM (Neurology)"], ["Migraine", "Epilepsy", "Stroke follow-up", "Nerve pain"]),
    "Psychiatrist": (["MD (Psychiatry)", "DPM"], ["Anxiety and depression", "Sleep problems", "Stress", "De-addiction"]),
    "Gastroenterologist": (["MD (Medicine), DM (Gastroenterology)"],
                           ["Acidity and reflux", "IBS", "Liver health", "Endoscopy review"]),
    "Endocrinologist": (["MD (Medicine), DM (Endocrinology)"], ["Diabetes", "Thyroid", "Obesity", "Hormone problems"]),
    "Pulmonologist": (["MD (Respiratory Medicine)", "DTCD"], ["Asthma", "COPD", "Sleep apnoea", "Persistent cough"]),
    "Urologist": (["MS (Surgery), MCh (Urology)"], ["Kidney stones", "Prostate", "Urinary infections", "Bladder problems"]),
    "Dentist": (["MDS (Conservative Dentistry)", "MDS (Orthodontics)"], ["Cleaning", "Fillings", "Root canal", "Braces consult"]),
}
HOSPITALS = ["Lilavati Hospital", "Hinduja Hospital", "Nanavati Max Hospital", "Kokilaben Hospital",
             "Breach Candy Hospital", "Jaslok Hospital", "Bombay Hospital", "Fortis Hiranandani", "Holy Family Hospital",
             "Wockhardt Hospital", "Saifee Hospital", None, None]
COLLEGES = ["Grant Medical College", "Seth GS Medical College", "LTMMC Sion", "Topiwala National Medical College",
            "BJ Medical College, Pune", "AFMC Pune", "Kasturba Medical College"]
BIO_ENDINGS = ["Believes in explaining every option before treatment.", "Known for unhurried consultations.",
               "Focuses on long-term care and prevention.", "Prefers conservative treatment where possible.",
               "Sees many families from the neighbourhood."]

# mundane things people jot down
DIARY_LINES = [
    "Walked to the market and bought mangoes. Too expensive this week.",
    "Train was 20 minutes late, read on the platform.",
    "Called Mummy, she says the plants are doing well.",
    "Cleaned the fridge finally. Found a very old lemon.",
    "Long day at work. Ordered pav bhaji, no regrets.",
    "Rain all evening. Stayed in and watched an old movie.",
    "Fixed the dripping tap with the neighbour's spanner.",
    "Went for a short walk at Shivaji Park after dinner.",
    "Paid the electricity bill and the society maintenance.",
    "Tried a new chai masala. Too much ginger.",
    "Slept early, phone on silent. Felt good.",
    "Helped my niece with her maths homework.",
    "Ironed clothes for the whole week while listening to the radio.",
    "Bought a new pillow, hoping it helps my neck.",
    "Lunch with old college friends in Dadar.",
    "Watered the tulsi plant. Pigeons back on the balcony.",
    "Power cut for two hours in the afternoon.",
    "Made poha for breakfast, forgot the peanuts.",
    "Sorted out old papers and found my school report card.",
    "Quiet day. Nothing much happened, which was nice.",
]

REVIEW_TEXT = {
    5: ["Excellent doctor, explained everything patiently.", "Very thorough and kind. Highly recommend.",
        "Diagnosis was spot on and the clinic ran on time.", "Best consultation I've had in years.",
        "Listened carefully and didn't rush. Great experience.", None],
    4: ["Good consultation, slight wait at the clinic.", "Helpful and knowledgeable, clinic a bit crowded.",
        "Clear explanation, would visit again.", "Nice doctor, reasonable fees.", None],
    3: ["Okay experience, waited almost an hour.", "Consultation felt a little rushed.",
        "Average. Treatment worked but communication could be better.", None],
    2: ["Long wait and very short consultation.", "Did not explain the prescription properly."],
    1: ["Very disappointing, appointment started 90 minutes late.", "Felt dismissed, won't return."],
}


def uid(rng: random.Random) -> uuid.UUID:
    return uuid.UUID(int=rng.getrandbits(128), version=4)


def local(d: date, t: time) -> datetime:
    return datetime.combine(d, t, tzinfo=TZ)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.getenv("DATABASE_URL", DEFAULT_URL).replace("+psycopg", ""))
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--reset", action="store_true", help="truncate all SALUS tables first")
    ap.add_argument("--if-empty", action="store_true", help="do nothing (exit 0) if data already exists")
    ap.add_argument("--patients", type=int, default=300)
    ap.add_argument("--history-days", type=int, default=120)
    ap.add_argument("--future-days", type=int, default=14)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    now = datetime.now(TZ)
    today = now.date()

    with psycopg.connect(args.url, autocommit=False) as conn, conn.cursor() as cur:
        cur.execute("SET timezone = 'Asia/Kolkata'")
        if args.reset:
            cur.execute("""TRUNCATE auth_sessions, accounts, diary_entries, doctor_profiles, medication_reminder_log, medication_reminders, medications, meals,
                           wellness_logs, reminders, reviews, appointments, doctor_unavailability,
                           doctor_schedules, doctors, specialties, patients RESTART IDENTITY CASCADE""")
        else:
            cur.execute("SELECT count(*) FROM doctors")
            if cur.fetchone()[0]:
                if args.if_empty:
                    print("Database already seeded; skipping.")
                    return
                sys.exit("Database already has data. Re-run with --reset to replace it.")

        # ---------------- specialties ----------------
        spec_ids = {}
        for name in SPECIALTIES:
            cur.execute("INSERT INTO specialties(name) VALUES (%s) RETURNING specialty_id", (name,))
            spec_ids[name] = cur.fetchone()[0]

        # ---------------- doctors ----------------
        used_emails: set[str] = set()

        def email_for(first, last, domain, prefix=""):
            base = f"{prefix}{first}.{last}".lower().replace("'", "").replace(" ", "")
            e, n = f"{base}@{domain}", 1
            while e in used_emails:
                n += 1
                e = f"{base}{n}@{domain}"
            used_emails.add(e)
            return e

        doctors = []  # dicts
        for spec, ((fee_lo, fee_hi), slot_min, count) in SPECIALTIES.items():
            for _ in range(count):
                female = rng.random() < 0.5
                first = rng.choice(FIRST_F if female else FIRST_M)
                last = rng.choice(LAST)
                area, lat, lon, pin = rng.choice(AREAS)
                lat += rng.uniform(-0.008, 0.008)
                lon += rng.uniform(-0.008, 0.008)
                d = dict(
                    id=uid(rng), name=f"{first} {last}", spec=spec, slot=slot_min,
                    email=email_for(first, last, "salusclinic.example", "dr."),
                    phone=f"+91 22 {rng.randint(2000, 6999)} {rng.randint(1000, 9999)}",
                    fee=round(rng.uniform(fee_lo, fee_hi) / 50) * 50,
                    lat=lat, lon=lon,
                    addr=f"{rng.randint(1, 40)}, {rng.choice(BUILDINGS)}, {rng.choice(STREETS)}, {area}, Mumbai {pin}",
                    quality=rng.uniform(2.8, 4.9),
                    popularity=rng.uniform(0.015, 0.05),
                )
                doctors.append(d)
                cur.execute(
                    """INSERT INTO doctors(doctor_id, full_name, email, phone, specialty_id, consultation_fee,
                                           location, address_text, created_at)
                       VALUES (%s,%s,%s,%s,%s,%s, ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography, %s, %s)""",
                    (d["id"], d["name"], d["email"], d["phone"], spec_ids[spec], d["fee"], d["lon"], d["lat"],
                     d["addr"], now - timedelta(days=rng.randint(200, 900))))

        # ---------------- weekly schedules ----------------
        PATTERNS = [
            [(time(10), time(13)), (time(17), time(20))],   # morning + evening clinic
            [(time(9), time(13))],
            [(time(11), time(15))],
            [(time(16), time(20, 30))],
            [(time(9, 30), time(12, 30)), (time(18), time(21))],
        ]
        schedules = defaultdict(list)  # doctor_id -> [(dow, start, end, slot)]
        for d in doctors:
            pattern = rng.choice(PATTERNS)
            off_days = {0} if rng.random() < 0.8 else {0, rng.choice([3, 4])}  # Sundays off mostly
            if rng.random() < 0.3:
                off_days.add(6)
            for dow in range(7):
                if dow in off_days:
                    continue
                blocks = pattern if dow != 6 else pattern[:1]   # Saturday: first block only
                for s, e in blocks:
                    schedules[d["id"]].append((dow, s, e, d["slot"]))
                    cur.execute("""INSERT INTO doctor_schedules(doctor_id, day_of_week, start_time, end_time, slot_minutes)
                                   VALUES (%s,%s,%s,%s,%s)""", (d["id"], dow, s, e, d["slot"]))

        # ---------------- leave / unavailability ----------------
        leave = defaultdict(list)  # doctor_id -> [(start, end)]
        for d in rng.sample(doctors, 22):
            for _ in range(rng.choice([1, 1, 2])):
                kind = rng.choice(["On leave", "Medical conference", "Personal leave", "Hospital duty",
                                   "Public holiday", "Workshop"])
                start_day = today + timedelta(days=rng.randint(-args.history_days, args.future_days))
                if kind in ("Hospital duty", "Workshop"):
                    st = local(start_day, time(rng.choice([10, 17])))
                    en = st + timedelta(hours=3)
                else:
                    st = local(start_day, time(0))
                    en = st + timedelta(days=rng.randint(1, 6))
                if any(st < e and s < en for s, e in leave[d["id"]]):
                    continue
                leave[d["id"]].append((st, en))
                cur.execute("""INSERT INTO doctor_unavailability(doctor_id, unavailable_range, reason)
                               VALUES (%s, tstzrange(%s,%s,'[)'), %s)""", (d["id"], st, en, kind))

        # ---------------- patients ----------------
        patients = []
        for _ in range(args.patients):
            female = rng.random() < 0.5
            first = rng.choice(FIRST_F if female else FIRST_M)
            last = rng.choice(LAST)
            age_days = rng.randint(4 * 365, 82 * 365) if rng.random() > 0.12 else rng.randint(365, 12 * 365)
            p = dict(
                id=uid(rng), name=f"{first} {last}",
                email=email_for(first, last, "example.com"),
                phone=f"+91 {rng.choice('6789')}{rng.randint(100000000, 999999999)}",
                dob=today - timedelta(days=age_days),
                diet=rng.choice(DIET_NOTES) if rng.random() < 0.45 else None,
                area=rng.choice(AREAS),
                adherence=rng.uniform(0.55, 0.98),
                mood_base=rng.uniform(4.5, 8.0),
                sleep_base=rng.uniform(5.5, 8.0),
                water_base=rng.randint(1200, 3000),
            )
            patients.append(p)
            cur.execute("""INSERT INTO patients(patient_id, full_name, email, phone, date_of_birth, dietary_notes, created_at)
                           VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                        (p["id"], p["name"], p["email"], p["phone"], p["dob"], p["diet"],
                         now - timedelta(days=rng.randint(args.history_days + 5, 700))))
        conn.commit()

        # ---------------- past appointments (historical import) ----------------
        # A patient's busy intervals, to avoid one patient in two places at once
        busy = defaultdict(list)
        # frequent visitors: a skewed patient pick so some have long histories
        weights = [rng.paretovariate(1.5) for _ in patients]

        def pick_patient(st, en):
            for _ in range(20):
                p = rng.choices(patients, weights)[0]
                if not any(st < e and s < en for s, e in busy[p["id"]]):
                    busy[p["id"]].append((st, en))
                    return p
            return None

        def on_leave(doc_id, st, en):
            return any(st < e and s < en for s, e in leave[doc_id])

        past_rows, review_rows, reminder_rows = [], [], []
        for offset in range(args.history_days, -1, -1):
            day = today - timedelta(days=offset)
            dow = (day.weekday() + 1) % 7   # python Mon=0 -> SQL Sun=0
            for d in doctors:
                for sdow, s, e, slot in schedules[d["id"]]:
                    if sdow != dow:
                        continue
                    t = local(day, s)
                    end_block = local(day, e)
                    while t + timedelta(minutes=slot) <= end_block:
                        st, en = t, t + timedelta(minutes=slot)
                        t = en
                        if en > now or on_leave(d["id"], st, en) or rng.random() > d["popularity"]:
                            continue
                        p = pick_patient(st, en)
                        if not p:
                            continue
                        status = rng.choices(["completed", "cancelled", "no_show"], [0.82, 0.11, 0.07])[0]
                        aid = uid(rng)
                        created = st - timedelta(days=rng.randint(1, 20), hours=rng.randint(0, 10))
                        past_rows.append((aid, p["id"], d["id"], Range(st, en, "[)"), status, created))
                        if status != "cancelled":
                            for h in (24, 2):
                                ra = st - timedelta(hours=h)
                                if ra > created:
                                    reminder_rows.append((aid, ra, ra + timedelta(seconds=rng.randint(1, 50))))
                        if status == "completed" and rng.random() < 0.68:
                            rating = max(1, min(5, round(rng.gauss(d["quality"], 0.8))))
                            review_rows.append((uid(rng), aid, p["id"], d["id"], rating,
                                                rng.choice(REVIEW_TEXT[rating]),
                                                min(now, en + timedelta(hours=rng.randint(1, 72)))))

        cur.executemany("""INSERT INTO appointments(appointment_id, patient_id, doctor_id, slot, status, created_at)
                           VALUES (%s,%s,%s,%s,%s,%s)""", past_rows)
        cur.executemany("INSERT INTO reminders(appointment_id, remind_at, sent_at) VALUES (%s,%s,%s)", reminder_rows)
        # reviews go through trg_validate_review + trg_refresh_doctor_rating
        cur.executemany("""INSERT INTO reviews(review_id, appointment_id, patient_id, doctor_id, rating, comment, created_at)
                           VALUES (%s,%s,%s,%s,%s,%s,%s)""", review_rows)
        conn.commit()

        # ---------------- future appointments via fn_book_appointment ----------------
        booked = 0
        for offset in range(0, args.future_days + 1):
            day = today + timedelta(days=offset)
            dow = (day.weekday() + 1) % 7
            for d in doctors:
                for sdow, s, e, slot in schedules[d["id"]]:
                    if sdow != dow:
                        continue
                    t = local(day, s)
                    while t + timedelta(minutes=slot) <= local(day, e):
                        st, en = t, t + timedelta(minutes=slot)
                        t = en
                        # demand falls off further into the future
                        p_book = d["popularity"] * 2.4 * (1 - offset / (args.future_days + 6))
                        if st <= now + timedelta(minutes=5) or on_leave(d["id"], st, en) or rng.random() > p_book:
                            continue
                        p = pick_patient(st, en)
                        if not p:
                            continue
                        cur.execute("SAVEPOINT b")
                        try:
                            cur.execute("SELECT appointment_id FROM fn_book_appointment(%s,%s,%s)",
                                        (p["id"], d["id"], st))
                            aid = cur.fetchone()[0]
                            cur.execute("RELEASE SAVEPOINT b")
                            booked += 1
                            if rng.random() < 0.06:
                                cur.execute("UPDATE appointments SET status='cancelled' WHERE appointment_id=%s", (aid,))
                        except psycopg.Error as exc:  # should not happen; keep going
                            cur.execute("ROLLBACK TO SAVEPOINT b")
                            print("booking skipped:", exc.diag.message_primary)
        conn.commit()

        # ---------------- medications ----------------
        med_rows, rem_rows, log_rows = [], [], []
        med_patients = rng.sample(patients, int(len(patients) * 0.7))
        for p in med_patients:
            n_meds = rng.choices([1, 2, 3, 4], [0.3, 0.35, 0.25, 0.1])[0]
            for drug, dosage, times, dows, chronic in rng.sample(DRUGS, n_meds):
                if chronic:
                    start = today - timedelta(days=rng.randint(40, 400))
                    end = None if rng.random() < 0.7 else today + timedelta(days=rng.randint(10, 120))
                else:
                    start = today + timedelta(days=rng.randint(-60, 5))
                    end = start + timedelta(days=rng.choice([5, 7, 10, 14, 21, 30]))
                mid = uid(rng)
                med_rows.append((mid, p["id"], drug, dosage, Range(start, end, "[)"),
                                 datetime.combine(start, time(10), TZ) - timedelta(days=1)))
                labels = {1: ["Daily dose"], 2: ["Morning dose", "Evening dose"],
                          3: ["Morning dose", "Afternoon dose", "Night dose"]}[len(times)]
                for hhmm, label in zip(times, labels):
                    mrid = uid(rng)
                    rem_rows.append((mrid, mid, time.fromisoformat(hhmm), dows or [0, 1, 2, 3, 4, 5, 6],
                                     label + (" - after food" if "after" in dosage else "")))
                    # 30 days of history (up to yesterday) in the dispatch log
                    for back in range(30, 0, -1):
                        dday = today - timedelta(days=back)
                        if dday < start or (end and dday >= end):
                            continue
                        if ((dday.weekday() + 1) % 7) not in (dows or range(7)):
                            continue
                        sent = local(dday, time.fromisoformat(hhmm)) + timedelta(seconds=rng.randint(1, 40))
                        r = rng.random()
                        taken = None if r < 0.04 else (r < p["adherence"])
                        log_rows.append((mrid, dday, sent, taken))

        cur.executemany("""INSERT INTO medications(medication_id, patient_id, drug_name, dosage, active_range, created_at)
                           VALUES (%s,%s,%s,%s,%s,%s)""", med_rows)
        cur.executemany("""INSERT INTO medication_reminders(medication_reminder_id, medication_id, reminder_time,
                                                            days_of_week, label) VALUES (%s,%s,%s,%s,%s)""", rem_rows)
        cur.executemany("""INSERT INTO medication_reminder_log(medication_reminder_id, reminder_date, sent_at, taken)
                           VALUES (%s,%s,%s,%s)""", log_rows)
        # today's rows come from the same functions pg_cron runs
        cur.execute("SELECT fn_generate_medication_reminder_log(CURRENT_DATE)")
        cur.execute("SELECT fn_dispatch_due_medication_reminders()")
        cur.execute("""UPDATE medication_reminder_log SET taken = (random() < 0.8)
                        WHERE reminder_date = CURRENT_DATE AND sent_at IS NOT NULL""")
        conn.commit()

        # ---------------- wellness logs (60 days) ----------------
        cur.execute("""SELECT patient_id, reminder_date, adherence_pct FROM v_daily_adherence""")
        adherence = {(r[0], r[1]): float(r[2]) for r in cur.fetchall()}
        well_rows = []
        for p in rng.sample(patients, int(len(patients) * 0.75)):
            completion = rng.uniform(0.6, 0.98)
            for back in range(60, -1, -1):
                dday = today - timedelta(days=back)
                if rng.random() > completion:
                    continue
                adh = adherence.get((p["id"], dday))
                weekend = dday.weekday() >= 5
                mood = p["mood_base"] + rng.gauss(0, 1.1) + (0.6 if weekend else 0)
                if adh is not None:            # a mild, visible association for the correlation demo
                    mood += (adh - 80) / 25
                sleep = p["sleep_base"] + rng.gauss(0, 0.8) + (0.7 if weekend else 0)
                water = p["water_base"] + rng.gauss(0, 350)
                well_rows.append((p["id"], dday, max(1, min(10, round(mood))),
                                  round(max(2.5, min(12, sleep)), 1), max(300, int(round(water, -1)))))
        cur.executemany("""INSERT INTO wellness_logs(patient_id, log_date, mood_score, sleep_hours, water_intake_ml)
                           VALUES (%s,%s,%s,%s,%s)""", well_rows)

        # ---------------- meals: 14 days logged + 7 days planned ----------------
        meal_rows = []
        by_type = defaultdict(list)
        for mt, desc, cal in MEALS:
            by_type[mt].append((desc, cal))
        for p in rng.sample(patients, int(len(patients) * 0.55)):
            ok = {mt: [m for m in items if not check_meal(m[0], p["diet"])] or items
                  for mt, items in by_type.items()}
            for back in range(-7, 15):                # negative = future (planned)
                dday = today - timedelta(days=back)
                planned = back < 0 or (back == 0 and rng.random() < 0.5)
                if not planned and rng.random() < 0.15:
                    continue                           # some days not logged
                for mt in ("breakfast", "lunch", "dinner", "snack"):
                    if mt == "snack" and rng.random() < 0.45:
                        continue
                    # logged (consumed) meals occasionally stray from the diet
                    pool = by_type[mt] if (not planned and rng.random() < 0.07) else ok[mt]
                    desc, cal = rng.choice(pool)
                    cal = int(cal * rng.uniform(0.85, 1.2))
                    meal_rows.append((p["id"], dday, mt, desc, cal, planned))
        cur.executemany("""INSERT INTO meals(patient_id, meal_date, meal_type, description, calories, is_planned)
                           VALUES (%s,%s,%s,%s,%s,%s)""", meal_rows)
        conn.commit()

        # ---------------- doctor profiles, diary, logins ----------------
        # own RNG so everything above stays identical to earlier versions of this script
        xr = random.Random(args.seed + 1)
        for d in doctors:
            pg, services = PROFILE[d["spec"]]
            since = today.year - xr.randint(4, 32)
            quals = ["BDS" if d["spec"] == "Dentist" else "MBBS", xr.choice(pg)]
            if xr.random() < 0.3:
                quals.append(xr.choice(["FRCP (London)", "Fellowship (AIIMS)", "MRCP (UK)", "Fellowship (Singapore)"]))
            hospital = xr.choice(HOSPITALS)
            bio = (f"Dr {d['name'].split()[-1]} has practised in Mumbai since {since}"
                   f"{' and also consults at ' + hospital if hospital else ''}. "
                   f"Trained at {xr.choice(COLLEGES)}. {xr.choice(BIO_ENDINGS)}")
            langs = ["English", "Hindi"] + xr.sample(["Marathi", "Gujarati", "Tamil", "Malayalam", "Bengali",
                                                     "Konkani", "Kannada", "Telugu", "Urdu"], xr.choice([1, 1, 2]))
            cur.execute("""INSERT INTO doctor_profiles (doctor_id, bio, qualifications, practising_since, languages,
                                                        services, hospital, registration_no)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (d["id"], bio, quals, since, langs, xr.sample(services, 3), hospital,
                         f"MMC {xr.randint(1990, 2022)}/{xr.randint(10000, 99999)}"))

        diary_rows = []
        for p in patients:
            if xr.random() < 0.4:
                continue
            for back in sorted(xr.sample(range(21), xr.randint(2, 7)), reverse=True):
                when = local(today - timedelta(days=back), time(xr.randint(7, 22), xr.choice([0, 15, 30, 45])))
                if when <= now:
                    diary_rows.append((p["id"], when.date(), xr.choice(DIARY_LINES), when, when))
        cur.executemany("""INSERT INTO diary_entries (patient_id, entry_date, body, created_at, updated_at)
                           VALUES (%s,%s,%s,%s,%s)""", diary_rows)

        cur.execute("SELECT fn_create_demo_accounts(%s)", (DEMO_PASSWORD,))
        conn.commit()

        # ---------------- summary ----------------
        print(f"Seeded SALUS (seed={args.seed}, today={today}):")
        for t in ["specialties", "doctors", "doctor_profiles", "doctor_schedules", "doctor_unavailability", "patients",
                  "appointments", "reviews", "reminders", "medications", "medication_reminders",
                  "medication_reminder_log", "meals", "wellness_logs", "diary_entries", "accounts"]:
            cur.execute(f"SELECT count(*) FROM {t}")
            print(f"  {t:<26}{cur.fetchone()[0]:>7}")
        cur.execute("SELECT status, count(*) FROM appointments GROUP BY 1 ORDER BY 1")
        print("  appointments by status:", dict(cur.fetchall()))
        print(f"  future bookings made through fn_book_appointment: {booked}")
        print(f"  every patient and doctor logs in with their email and the password '{DEMO_PASSWORD}'")


if __name__ == "__main__":
    main()
