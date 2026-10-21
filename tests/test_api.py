"""End-to-end tests against a running API (seeded DB).

    uvicorn app.main:app --port 8000     # in backend/
    pytest -v tests/                     # in the project root

Each test creates its own patient / doctor, so it can be run repeatedly.
"""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

import httpx
import pytest

BASE = os.getenv("SALUS_API", "http://localhost:8000")
api = httpx.Client(base_url=BASE, timeout=30)


def ok(r: httpx.Response, status=200):
    assert r.status_code == status, f"{r.status_code}: {r.text}"
    return r.json()


def new_patient(diet=None):
    tag = uuid.uuid4().hex[:8]
    return ok(api.post("/patients", json={"full_name": f"Test Patient {tag}", "email": f"t{tag}@example.com",
                                          "dietary_notes": diet}), 201)


@pytest.fixture(scope="module")
def doctor():
    tag = uuid.uuid4().hex[:8]
    spec = ok(api.get("/specialties"))[0]["specialty_id"]
    return ok(api.post("/doctors", json={
        "full_name": f"Test Doctor {tag}", "email": f"doc{tag}@example.com", "specialty_id": spec,
        "consultation_fee": 700, "latitude": 19.06, "longitude": 72.83, "address_text": "Test clinic, Bandra",
        "schedule": [{"day_of_week": d, "start_time": "09:00", "end_time": "21:00", "slot_minutes": 30}
                     for d in range(7)]}), 201)


def free_slots(doctor_id, days_ahead=1, n=1):
    d = (date.today() + timedelta(days=days_ahead)).isoformat()
    return ok(api.get(f"/doctors/{doctor_id}/slots", params={"date": d}))[d][:n]


# ---------------------------------------------------------------- search
def test_search_ranks_by_composite_score():
    rows = ok(api.get("/doctors/search", params={"lat": 19.0178, "lon": 72.8478, "specialty": "Cardiologist",
                                                  "max_budget": 2500, "radius_km": 40}))
    assert rows and all(r["specialty"] == "Cardiologist" for r in rows)
    scores = [float(r["composite_score"]) for r in rows]
    assert scores == sorted(scores, reverse=True)


def test_search_weights_change_order():
    p = {"lat": 19.0178, "lon": 72.8478, "radius_km": 40, "include_next_available": False, "limit": 5}
    cheap = ok(api.get("/doctors/search", params={**p, "w_distance": 0, "w_fee": 1, "w_rating": 0}))
    fees = [float(r["consultation_fee"]) for r in cheap]
    assert fees == sorted(fees)


def test_within_budget_filter():
    rows = ok(api.get("/doctors/search", params={"lat": 19.1, "lon": 72.85, "max_budget": 600,
                                                  "within_budget": True, "radius_km": 50}))
    assert all(float(r["consultation_fee"]) <= 600 for r in rows)


# ---------------------------------------------------------------- booking
def test_book_and_slot_disappears(doctor):
    p = new_patient()
    slot = free_slots(doctor["doctor_id"])[0]
    a = ok(api.post("/appointments", json={"patient_id": p["patient_id"], "doctor_id": doctor["doctor_id"],
                                           "start_at": slot["slot_start"]}), 201)
    assert a["status"] == "scheduled"
    day = slot["slot_start"][:10]
    starts = [s["slot_start"] for s in ok(api.get(f"/doctors/{doctor['doctor_id']}/slots", params={"date": day}))[day]]
    assert slot["slot_start"] not in starts
    # reminders created by trigger (24h and/or 2h before)
    assert ok(api.get(f"/appointments/{a['appointment_id']}/reminders"))


def test_concurrent_booking_only_one_wins(doctor):
    """20 different patients race for the same slot at the same moment."""
    slot = free_slots(doctor["doctor_id"], days_ahead=2)[0]
    patients = [new_patient() for _ in range(20)]

    def attempt(p):
        with httpx.Client(base_url=BASE, timeout=30) as c:
            return c.post("/appointments", json={"patient_id": p["patient_id"], "doctor_id": doctor["doctor_id"],
                                                 "start_at": slot["slot_start"]}).status_code

    with ThreadPoolExecutor(max_workers=20) as ex:
        codes = list(ex.map(attempt, patients))
    assert codes.count(201) == 1, codes
    assert codes.count(409) == 19, codes


def test_cancel_frees_slot_for_rebooking(doctor):
    p1, p2 = new_patient(), new_patient()
    slot = free_slots(doctor["doctor_id"], days_ahead=3)[0]
    body = {"doctor_id": doctor["doctor_id"], "start_at": slot["slot_start"]}
    a = ok(api.post("/appointments", json={**body, "patient_id": p1["patient_id"]}), 201)
    assert api.post("/appointments", json={**body, "patient_id": p2["patient_id"]}).status_code == 409
    ok(api.post(f"/appointments/{a['appointment_id']}/cancel"))
    ok(api.post("/appointments", json={**body, "patient_id": p2["patient_id"]}), 201)


def test_rejects_outside_schedule_misaligned_past_and_leave(doctor):
    p = new_patient()
    tomorrow = date.today() + timedelta(days=1)
    base = {"patient_id": p["patient_id"], "doctor_id": doctor["doctor_id"]}
    for start in (f"{tomorrow}T06:00:00+05:30",          # before hours
                  f"{tomorrow}T10:10:00+05:30",          # not on the 30-min grid
                  f"{date.today() - timedelta(days=1)}T10:00:00+05:30"):  # past
        r = api.post("/appointments", json={**base, "start_at": start})
        assert r.status_code == 422, r.text
    # leave blocks booking
    d5 = date.today() + timedelta(days=5)
    leave = ok(api.post(f"/doctors/{doctor['doctor_id']}/unavailability", json={
        "start_at": f"{d5}T00:00:00+05:30", "end_at": f"{d5 + timedelta(days=1)}T00:00:00+05:30",
        "reason": "Conference"}), 201)
    assert ok(api.get(f"/doctors/{doctor['doctor_id']}/slots", params={"date": d5.isoformat()}))[d5.isoformat()] == []
    r = api.post("/appointments", json={**base, "start_at": f"{d5}T10:00:00+05:30"})
    assert r.status_code == 422 and "unavailable" in r.json()["detail"]
    # overlapping leave -> 409 from EXCLUDE constraint
    r = api.post(f"/doctors/{doctor['doctor_id']}/unavailability", json={
        "start_at": f"{d5}T12:00:00+05:30", "end_at": f"{d5}T14:00:00+05:30"})
    assert r.status_code == 409
    api.delete(f"/doctors/{doctor['doctor_id']}/unavailability/{leave['unavailability_id']}")


def test_patient_cannot_be_in_two_places(doctor):
    p = new_patient()
    slot = free_slots(doctor["doctor_id"], days_ahead=4)[0]
    ok(api.post("/appointments", json={"patient_id": p["patient_id"], "doctor_id": doctor["doctor_id"],
                                       "start_at": slot["slot_start"]}), 201)
    # find another doctor working at that exact time
    other = next(d for d in ok(api.get("/doctors", params={"limit": 200}))
                 if slot["slot_start"] in [s["slot_start"] for s in ok(api.get(
                     f"/doctors/{d['doctor_id']}/slots", params={"date": slot["slot_start"][:10]})).popitem()[1]])
    r = api.post("/appointments", json={"patient_id": p["patient_id"], "doctor_id": other["doctor_id"],
                                        "start_at": slot["slot_start"]})
    assert r.status_code == 422 and "another appointment" in r.json()["detail"]


def test_cannot_complete_future_appointment(doctor):
    p = new_patient()
    slot = free_slots(doctor["doctor_id"], days_ahead=6)[0]
    a = ok(api.post("/appointments", json={"patient_id": p["patient_id"], "doctor_id": doctor["doctor_id"],
                                           "start_at": slot["slot_start"]}), 201)
    assert api.post(f"/appointments/{a['appointment_id']}/complete").status_code == 422


# ---------------------------------------------------------------- reviews
def _seeded_appointment(status, reviewed=False):
    rows = ok(api.get("/appointments", params={"status": status, "limit": 300}))
    return next(a for a in rows if a["has_review"] == reviewed)


def test_review_only_after_completed_appointment(doctor):
    sched = ok(api.get("/appointments", params={"status": "scheduled", "limit": 1}))[0]
    r = api.post("/reviews", json={"appointment_id": sched["appointment_id"], "patient_id": sched["patient_id"],
                                   "rating": 5})
    assert r.status_code == 422 and "not completed" in r.json()["detail"]


def test_review_patient_must_match_and_rating_updates():
    appt = _seeded_appointment("completed", reviewed=False)
    stranger = new_patient()
    r = api.post("/reviews", json={"appointment_id": appt["appointment_id"], "patient_id": stranger["patient_id"],
                                   "rating": 1})
    assert r.status_code == 422
    before = ok(api.get(f"/doctors/{appt['doctor_id']}"))
    ok(api.post("/reviews", json={"appointment_id": appt["appointment_id"], "patient_id": appt["patient_id"],
                                  "rating": 5, "comment": "Great"}), 201)
    after = ok(api.get(f"/doctors/{appt['doctor_id']}"))
    assert after["rating_count"] == before["rating_count"] + 1
    # second review of same appointment -> 409
    r = api.post("/reviews", json={"appointment_id": appt["appointment_id"], "patient_id": appt["patient_id"],
                                   "rating": 4})
    assert r.status_code == 409


# ---------------------------------------------------------------- medications
def test_medication_overlap_detection_and_doses():
    p = new_patient()
    today = date.today()
    m1 = ok(api.post(f"/patients/{p['patient_id']}/medications", json={
        "drug_name": "Amoxicillin 500mg", "dosage": "1 capsule thrice daily",
        "start_date": str(today - timedelta(days=2)), "end_date": str(today + timedelta(days=5)),
        "reminders": [{"reminder_time": "00:01", "label": "Midnight test dose"}, {"reminder_time": "23:59"}]}), 201)
    assert m1["overlaps"] == [] and m1["is_active_today"]
    m2 = ok(api.post(f"/patients/{p['patient_id']}/medications", json={
        "drug_name": "Paracetamol 650mg", "dosage": "1 tablet as needed",
        "start_date": str(today + timedelta(days=3)), "end_date": None}), 201)
    assert len(m2["overlaps"]) == 1 and m2["overlaps"][0]["overlap_days"] == 2
    assert len(ok(api.get(f"/patients/{p['patient_id']}/medications/overlaps"))) == 1
    # dispatch -> the 00:01 dose is due and gets sent
    ok(api.post("/admin/dispatch"))
    doses = ok(api.get(f"/patients/{p['patient_id']}/doses"))
    sent = [d for d in doses if d["sent_at"]]
    assert sent and sent[0]["label"] == "Midnight test dose"
    ok(api.post(f"/medication-log/{sent[0]['log_id']}", json={"taken": True}))
    adh = ok(api.get(f"/patients/{p['patient_id']}/adherence"))
    assert adh[-1]["doses_taken"] == 1
    # stop medication
    upd = ok(api.patch(f"/medications/{m1['medication_id']}", json={"end_date": str(today + timedelta(days=1))}))
    assert upd["end_date"] == str(today + timedelta(days=1))


# ---------------------------------------------------------------- meals & wellness
def test_meal_diet_conflicts():
    p = new_patient(diet="Vegetarian, lactose intolerant")
    m = ok(api.post(f"/patients/{p['patient_id']}/meals", json={
        "meal_date": str(date.today()), "meal_type": "dinner", "description": "Chicken curry with raita",
        "calories": 650, "is_planned": False}), 201)
    assert any("Vegetarian" in c for c in m["diet_conflicts"])
    assert any("Lactose" in c for c in m["diet_conflicts"])
    ok_meal = ok(api.post(f"/patients/{p['patient_id']}/meals", json={
        "meal_date": str(date.today()), "meal_type": "lunch", "description": "Dal tadka, jeera rice and salad",
        "calories": 520}), 201)
    assert ok_meal["diet_conflicts"] == []
    summary = ok(api.get(f"/patients/{p['patient_id']}/meals/summary"))
    today = next(s for s in summary if s["meal_date"] == str(date.today()))
    assert today["diet_conflicts"] == 1 and today["consumed_calories"] == 650


def test_wellness_upsert_and_trend():
    p = new_patient()
    for i in range(10):
        d = date.today() - timedelta(days=i)
        ok(api.put(f"/patients/{p['patient_id']}/wellness/{d}",
                   json={"mood_score": 5 + (i % 3), "sleep_hours": 7, "water_intake_ml": 2000}))
    # upsert same day again
    ok(api.put(f"/patients/{p['patient_id']}/wellness/{date.today()}", json={"mood_score": 9}))
    trend = ok(api.get(f"/patients/{p['patient_id']}/wellness/trend",
                       params={"from": str(date.today() - timedelta(days=3))}))
    assert len(trend) == 4 and trend[-1]["mood_score"] == 9
    assert trend[0]["days_logged_7d"] == 7          # window reached back before 'from'
    assert api.put(f"/patients/{p['patient_id']}/wellness/{date.today()}", json={"mood_score": 11}).status_code == 422


def test_seeded_patient_dashboard_and_correlation():
    # a seeded patient who has both medications and wellness logs
    stats = ok(api.get("/admin/stats"))
    assert stats["patients"] >= 300 and stats["doctors"] >= 70
    for p in ok(api.get("/patients", params={"limit": 300})):
        corr = ok(api.get(f"/patients/{p['patient_id']}/wellness/adherence-correlation"))
        if corr["days_compared"] >= 15:
            break
    assert corr["days_compared"] >= 15
    dash = ok(api.get(f"/patients/{p['patient_id']}/dashboard"))
    assert dash["active_medications"]


# ---------------------------------------------------------------- login, diary, doctor profiles
def register(diet=None):
    tag = uuid.uuid4().hex[:8]
    return ok(api.post("/auth/register", json={"full_name": f"Login Test {tag}", "email": f"login{tag}@example.com",
                                               "password": "correct horse", "dietary_notes": diet}), 201)


def auth(s):
    return {"Authorization": f"Bearer {s['token']}"}


def test_register_login_and_logout():
    s = register()
    assert s["role"] == "patient" and s["patient"]["patient_id"] == s["patient_id"]
    assert api.post("/auth/login", json={"email": s["email"], "password": "wrong password"}).status_code == 401
    again = ok(api.post("/auth/login", json={"email": s["email"].upper(), "password": "correct horse"}))
    assert ok(api.get("/auth/me", headers=auth(again)))["account_id"] == s["account_id"]
    assert api.post("/auth/logout", headers=auth(again)).status_code == 204
    assert api.get("/auth/me", headers=auth(again)).status_code == 401
    assert api.get("/auth/me", headers=auth(s)).status_code == 200          # other sessions survive
    r = api.post("/auth/register", json={"full_name": "Dup", "email": s["email"], "password": "whatever123"})
    assert r.status_code == 409


def test_diary_is_private():
    me, other = register(), register()
    url = f"/patients/{me['patient_id']}/diary"
    assert api.get(url).status_code == 401
    e = ok(api.post(url, headers=auth(me), json={"body": "  Bought vegetables, forgot coriander.  "}), 201)
    assert e["body"] == "Bought vegetables, forgot coriander." and e["entry_date"] == ok(api.get("/health"))["db_time"][:10]
    assert [x["entry_id"] for x in ok(api.get(url, headers=auth(me)))] == [e["entry_id"]]
    assert api.get(url, headers=auth(other)).status_code == 403
    assert api.patch(f"/diary/{e['entry_id']}", headers=auth(other), json={"body": "hacked"}).status_code == 404
    assert ok(api.patch(f"/diary/{e['entry_id']}", headers=auth(me), json={"body": "Got coriander too."}))["body"] \
        == "Got coriander too."
    future = (date.today() + timedelta(days=3)).isoformat()
    assert api.post(url, headers=auth(me), json={"body": "x", "entry_date": future}).status_code == 422
    assert api.post(url, headers=auth(me), json={"body": ""}).status_code == 422
    assert api.delete(f"/diary/{e['entry_id']}", headers=auth(me)).status_code == 204
    assert ok(api.get(url, headers=auth(me))) == []


def test_doctor_edits_only_own_profile():
    demo = [a for a in ok(api.get("/auth/demo-accounts")) if a["role"] == "doctor"]
    if not demo:
        pytest.skip("demo mode is off")
    s = ok(api.post("/auth/login", json={"email": demo[0]["email"], "password": "salus123"}))
    did = s["doctor_id"]
    before = ok(api.get(f"/doctors/{did}"))["profile"]
    body = {"bio": "Test bio", "qualifications": ["MBBS", " ", "MD"], "practising_since": 2010,
            "languages": ["English"], "services": [], "hospital": None, "registration_no": "MMC 1/1"}
    saved = ok(api.put(f"/doctors/{did}/profile", headers=auth(s), json=body))
    assert saved["qualifications"] == ["MBBS", "MD"] and saved["years_experience"] == date.today().year - 2010
    assert ok(api.get(f"/doctors/{did}"))["profile"]["bio"] == "Test bio"
    patient = register()
    assert api.put(f"/doctors/{did}/profile", headers=auth(patient), json=body).status_code == 403
    assert api.put(f"/doctors/{did}/profile", json=body).status_code == 401
    if before:  # put the seeded profile back
        restore = {k: before[k] for k in ("bio", "qualifications", "practising_since", "languages", "services",
                                          "hospital", "registration_no")}
        ok(api.put(f"/doctors/{did}/profile", headers=auth(s), json=restore))
