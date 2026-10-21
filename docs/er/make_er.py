"""Generates the SALUS ER diagram (Chen notation) as SVG.

    python docs/er/make_er.py            -> docs/er/salus_er.svg

Layout is hand-placed: every entity, relationship and attribute position is
set below, so the picture stays stable and readable.
"""
import base64
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
FONT = HERE.parents[1] / "frontend/node_modules/@fontsource-variable/public-sans/files/public-sans-latin-wght-normal.woff2"

W, H = 3150, 1900
INK = "#18221F"
ENT_FILL = "#D9E8E3"
REL_FILL = "#FCF1C9"
ATT_FILL = "#FFFFFF"

# ---------------------------------------------------------------- model
# name: (x, y, [ (label, kind, angle_deg, dist) ])  angle 0 = right, 90 = up
#   kind: key | plain | derived | multi
ENTITIES = {
    "SPECIALTY": (900, 230, [
        ("specialty_id", "key", 180, 205), ("name", "plain", 0, 190)]),
    "DOCTOR": (900, 900, [
        ("doctor_id", "key", 287, 150), ("full_name", "plain", 252, 225), ("email", "plain", 226, 268),
        ("consultation_fee", "plain", 307, 245), ("location", "plain", 333, 200),
        ("phone", "plain", 116, 172), ("address_text", "plain", 135, 250),
        ("average_rating", "derived", 30, 250), ("rating_count", "derived", 60, 215)]),
    "DOCTOR_SCHEDULE": (300, 560, [
        ("schedule_id", "key", 90, 110), ("start_time", "plain", 150, 185), ("end_time", "plain", 195, 215),
        ("day_of_week", "plain", 235, 170), ("slot_minutes", "plain", 290, 115)]),
    "DOCTOR_UNAVAILABILITY": (340, 1250, [
        ("unavailability_id", "key", 270, 110), ("unavailable_range", "plain", 205, 235), ("reason", "plain", 150, 190)]),
    "APPOINTMENT": (1500, 900, [
        ("appointment_id", "key", 90, 135), ("status", "plain", 150, 175), ("slot", "plain", 30, 165)]),
    "REVIEW": (1150, 1500, [
        ("review_id", "key", 205, 200), ("rating", "plain", 270, 115), ("comment", "plain", 335, 195)]),
    "REMINDER": (1720, 1500, [
        ("reminder_id", "key", 205, 210), ("remind_at", "plain", 265, 120), ("sent_at", "plain", 315, 170)]),
    "PATIENT": (2200, 900, [
        ("patient_id", "key", 150, 205), ("full_name", "plain", 118, 175), ("date_of_birth", "plain", 212, 205),
        ("email", "plain", 30, 190), ("phone", "plain", 58, 185), ("dietary_notes", "plain", 2, 250)]),
    "MEDICATION": (2200, 300, [
        ("medication_id", "key", 90, 115), ("drug_name", "plain", 155, 215),
        ("dosage", "plain", 200, 220), ("active_range", "plain", 238, 200)]),
    "MEDICATION_REMINDER": (2820, 300, [
        ("medication_reminder_id", "key", 90, 110), ("days_of_week", "multi", 225, 210),
        ("label", "plain", 30, 240), ("reminder_time", "plain", 330, 215)]),
    "MEDICATION_REMINDER_LOG": (2820, 900, [
        ("log_id", "key", 0, 240), ("reminder_date", "plain", 322, 200), ("sent_at", "plain", 270, 115),
        ("taken", "plain", 218, 205)]),
    "MEAL": (2220, 1500, [
        ("meal_id", "key", 200, 235), ("meal_date", "plain", 235, 200), ("meal_type", "plain", 270, 120),
        ("description", "plain", 305, 190), ("calories", "plain", 335, 235), ("is_planned", "plain", 22, 215)]),
    "WELLNESS_LOG": (2800, 1500, [
        ("log_id", "key", 0, 205), ("log_date", "plain", 322, 190), ("mood_score", "plain", 270, 115),
        ("sleep_hours", "plain", 222, 200), ("water_intake_ml", "plain", 52, 160)]),
}

# (label, x, y, entity_a, card_a, total_a, entity_b, card_b, total_b)
#   total_* = total participation (double line) on that side
RELS = [
    ("has", 900, 560, "SPECIALTY", "1", False, "DOCTOR", "N", True),
    ("works", 560, 735, "DOCTOR", "1", False, "DOCTOR_SCHEDULE", "N", True),
    ("takes leave", 560, 1075, "DOCTOR", "1", False, "DOCTOR_UNAVAILABILITY", "N", True),
    ("receives", 1200, 900, "DOCTOR", "1", False, "APPOINTMENT", "N", True),
    ("books", 1850, 900, "PATIENT", "1", False, "APPOINTMENT", "N", True),
    ("yields", 1330, 1210, "APPOINTMENT", "1", False, "REVIEW", "0..1", True),
    ("triggers", 1620, 1210, "APPOINTMENT", "1", False, "REMINDER", "N", True),
    ("tracks", 2200, 600, "PATIENT", "1", False, "MEDICATION", "N", True),
    ("scheduled at", 2510, 300, "MEDICATION", "1", False, "MEDICATION_REMINDER", "N", True),
    ("generates", 2820, 600, "MEDICATION_REMINDER", "1", False, "MEDICATION_REMINDER_LOG", "N", True),
    ("plans", 2210, 1210, "PATIENT", "1", False, "MEAL", "N", True),
    ("records", 2510, 1210, "PATIENT", "1", False, "WELLNESS_LOG", "N", True),
]

# ---------------------------------------------------------------- geometry
CH = 9.6  # approx. glyph width at 17px


def ent_size(name):
    return max(160, len(name) * 13.6 + 40), 58


def rel_size(label):
    return max(130, len(label) * 11 + 70), 76


def att_size(label):
    return len(label) * 4.45 + 22, 22


def edge_point(cx, cy, w, h, tx, ty, shape):
    """Where the line from the centre towards (tx, ty) leaves the shape."""
    dx, dy = tx - cx, ty - cy
    if dx == 0 and dy == 0:
        return cx, cy
    if shape == "rect":
        s = min((w / 2) / abs(dx) if dx else 1e9, (h / 2) / abs(dy) if dy else 1e9)
    elif shape == "diamond":
        s = 1 / (abs(dx) / (w / 2) + abs(dy) / (h / 2))
    else:  # ellipse
        s = 1 / math.sqrt((dx / w) ** 2 + (dy / h) ** 2)
    return cx + dx * s, cy + dy * s


def line(x1, y1, x2, y2, double=False):
    if not double:
        return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" class="ln"/>'
    L = math.hypot(x2 - x1, y2 - y1) or 1
    ox, oy = -(y2 - y1) / L * 3.2, (x2 - x1) / L * 3.2
    return (f'<line x1="{x1+ox:.1f}" y1="{y1+oy:.1f}" x2="{x2+ox:.1f}" y2="{y2+oy:.1f}" class="ln"/>'
            f'<line x1="{x1-ox:.1f}" y1="{y1-oy:.1f}" x2="{x2-ox:.1f}" y2="{y2-oy:.1f}" class="ln"/>')


def build():
    out_lines, out_shapes, out_labels = [], [], []

    # attributes
    for name, (x, y, atts) in ENTITIES.items():
        ew, eh = ent_size(name)
        for label, kind, ang, dist in atts:
            a = math.radians(ang)
            ax, ay = x + math.cos(a) * dist, y - math.sin(a) * dist
            rx, ry = att_size(label)
            p1 = edge_point(x, y, ew, eh, ax, ay, "rect")
            p2 = edge_point(ax, ay, rx, ry, x, y, "ellipse")
            out_lines.append(line(*p1, *p2))
            dash = ' stroke-dasharray="6 4"' if kind == "derived" else ""
            out_shapes.append(f'<ellipse cx="{ax:.1f}" cy="{ay:.1f}" rx="{rx:.1f}" ry="{ry}" class="att"{dash}/>')
            if kind == "multi":
                out_shapes.append(f'<ellipse cx="{ax:.1f}" cy="{ay:.1f}" rx="{rx-5:.1f}" ry="{ry-5}" class="att2"/>')
            deco = ' text-decoration="underline"' if kind == "key" else ""
            weight = ' font-weight="650"' if kind == "key" else ""
            out_labels.append(f'<text x="{ax:.1f}" y="{ay+5.5:.1f}" class="t-att"{deco}{weight}>{label}</text>')

    # relationships
    for label, rx, ry, ea, ca, ta, eb, cb, tb in RELS:
        dw, dh = rel_size(label)
        for ent, card, total in ((ea, ca, ta), (eb, cb, tb)):
            ex, ey, _ = ENTITIES[ent]
            ew, eh = ent_size(ent)
            p1 = edge_point(ex, ey, ew, eh, rx, ry, "rect")
            p2 = edge_point(rx, ry, dw, dh, ex, ey, "diamond")
            out_lines.append(line(*p1, *p2, double=total))
            # cardinality label, near the entity end of the line, nudged sideways
            L = math.hypot(p2[0] - p1[0], p2[1] - p1[1]) or 1
            ux, uy = (p2[0] - p1[0]) / L, (p2[1] - p1[1]) / L
            t = min(34, L * 0.35)
            cx, cy = p1[0] + ux * t - uy * 16, p1[1] + uy * t + ux * 16
            out_labels.append(f'<text x="{cx:.1f}" y="{cy+6:.1f}" class="t-card">{card}</text>')
        pts = f"{rx},{ry-dh/2} {rx+dw/2},{ry} {rx},{ry+dh/2} {rx-dw/2},{ry}"
        out_shapes.append(f'<polygon points="{pts}" class="rel"/>')
        out_labels.append(f'<text x="{rx}" y="{ry+6}" class="t-rel">{label}</text>')

    # entities
    for name, (x, y, _) in ENTITIES.items():
        ew, eh = ent_size(name)
        out_shapes.append(f'<rect x="{x-ew/2:.1f}" y="{y-eh/2}" width="{ew:.1f}" height="{eh}" rx="3" class="ent"/>')
        out_labels.append(f'<text x="{x}" y="{y+7}" class="t-ent">{name}</text>')

    font = base64.b64encode(FONT.read_bytes()).decode() if FONT.exists() else None
    font_css = (f"@font-face{{font-family:'ERSans';src:url(data:font/woff2;base64,{font}) format('woff2');font-weight:100 900;}}"
                if font else "")
    legend = legend_svg(40, 40)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="ERSans, 'Public Sans', Arial, sans-serif">
<style>{font_css}
.ln{{stroke:{INK};stroke-width:1.6}}
.ent{{fill:{ENT_FILL};stroke:{INK};stroke-width:2.2}}
.rel{{fill:{REL_FILL};stroke:{INK};stroke-width:2}}
.att{{fill:{ATT_FILL};stroke:{INK};stroke-width:1.5}}
.att2{{fill:none;stroke:{INK};stroke-width:1.3}}
text{{fill:{INK};text-anchor:middle}}
.t-ent{{font-size:20px;font-weight:750;letter-spacing:.02em}}
.t-rel{{font-size:18px;font-weight:600;font-style:italic}}
.t-att{{font-size:16px}}
.t-card{{font-size:19px;font-weight:750;fill:#1E5A50}}
.t-title{{font-size:34px;font-weight:750;text-anchor:start}}
.t-sub{{font-size:17px;text-anchor:start;fill:#4A5752}}
.t-leg{{font-size:16px;text-anchor:start}}
</style>
<rect width="{W}" height="{H}" fill="#fff"/>
<text x="40" y="1820" class="t-title">SALUS: Entity-Relationship diagram</text>
<text x="40" y="1856" class="t-sub">Chen notation. 13 entities, 12 relationships. created_at timestamps are omitted for clarity; foreign keys are shown by relationships, not as attributes.</text>
{''.join(out_lines)}
{''.join(out_shapes)}
{''.join(out_labels)}
{legend}
</svg>'''


def legend_svg(x, y):
    """Notation key, drawn in the empty top-left corner."""
    r = []
    r.append(f'<rect x="{x}" y="{y}" width="560" height="300" rx="10" fill="#F6F9F7" stroke="#CFD8D3"/>')
    r.append(f'<text x="{x+22}" y="{y+38}" class="t-leg" font-weight="750" font-size="19">Notation</text>')
    c1, c2 = x + 22, x + 290
    rows = [
        (c1, y + 78, f'<rect x="{c1}" y="{y+62}" width="70" height="32" rx="3" class="ent"/>', "Entity"),
        (c1, y + 128, f'<polygon points="{c1+35},{y+110} {c1+70},{y+128} {c1+35},{y+146} {c1},{y+128}" class="rel"/>', "Relationship"),
        (c1, y + 178, f'<ellipse cx="{c1+35}" cy="{y+178}" rx="35" ry="16" class="att"/>', "Attribute"),
        (c1, y + 228, f'<ellipse cx="{c1+35}" cy="{y+228}" rx="35" ry="16" class="att"/><text x="{c1+35}" y="{y+233}" class="t-att" text-decoration="underline" font-weight="650">id</text>', "Key attribute"),
        (c2, y + 78, f'<ellipse cx="{c2+35}" cy="{y+78}" rx="35" ry="16" class="att" stroke-dasharray="6 4"/>', "Derived (kept by trigger)"),
        (c2, y + 128, f'<ellipse cx="{c2+35}" cy="{y+128}" rx="35" ry="16" class="att"/><ellipse cx="{c2+35}" cy="{y+128}" rx="29" ry="11" class="att2"/>', "Multivalued"),
        (c2, y + 178, line(c2, y + 178, c2 + 70, y + 178, True), "Total participation"),
        (c2, y + 228, line(c2, y + 228, c2 + 70, y + 228), "Partial participation"),
    ]
    for cx, cy, shape, label in rows:
        r.append(shape)
        r.append(f'<text x="{cx+86}" y="{cy+6}" class="t-leg">{label}</text>')
    r.append(f'<text x="{c1}" y="{y+278}" class="t-leg"><tspan class="t-card" font-size="17">1</tspan>, <tspan class="t-card" font-size="17">N</tspan>, <tspan class="t-card" font-size="17">0..1</tspan>  cardinality: how many of that entity take part</text>')
    return "".join(r)


if __name__ == "__main__":
    svg = build()
    (HERE / "salus_er.svg").write_text(svg)
    print("wrote", HERE / "salus_er.svg", len(svg) // 1024, "KB")
