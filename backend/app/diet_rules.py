"""Keyword rules that cross-reference a meal description with a patient's
free-text dietary notes. Deliberately simple and transparent: it flags a
meal when its description mentions an ingredient the note rules out.
It is a convenience check, not nutritional advice.
"""
from __future__ import annotations

import re

MEAT = ["chicken", "mutton", "fish", "prawn", "keema", "lamb", "pork", "beef", "crab", "surmai", "pomfret", "bombil"]
EGG = ["egg", "omelette", "anda"]
DAIRY = ["paneer", "curd", "dahi", "milk", "ghee", "cheese", "butter", "lassi", "raita",
         "kheer", "buttermilk", "chaas", "cream", "shrikhand", "malai", "yogurt"]
GLUTEN = ["roti", "chapati", "paratha", "naan", "bread", "wheat", "pasta", "poori", "puri",
          "rava", "semolina", "sandwich", "thepla", "kulcha", "pav", "upma", "sheera", "daliya", "noodles"]
NUTS = ["peanut", "cashew", "almond", "kaju", "walnut", "badam", "groundnut", "pista"]
SUGAR = ["jalebi", "gulab jamun", "kheer", "ladoo", "halwa", "sheera", "mango shake", "sweet", "shrikhand", "sugar"]
ROOT_ONION_GARLIC = ["onion", "garlic", "potato", "aloo", "carrot", "beetroot", "radish", "mooli"]
HIGH_SALT = ["pickle", "papad", "chips", "instant noodles", "achar"]

# (pattern found in dietary_notes) -> (rule label, forbidden keywords)
RULES: list[tuple[str, str, list[str]]] = [
    (r"\bvegan\b", "Vegan", MEAT + EGG + DAIRY),
    (r"\bjain\b", "Jain", MEAT + EGG + ROOT_ONION_GARLIC),
    (r"\beggetarian\b", "Eggetarian", MEAT),
    (r"\bvegetarian\b", "Vegetarian", MEAT + EGG),
    (r"lactose|dairy[- ]free|no dairy", "Lactose-free", DAIRY),
    (r"gluten|celiac|coeliac", "Gluten-free", GLUTEN),
    (r"\bnut\b|nuts|peanut", "Nut-free", NUTS),
    (r"low sugar|diabet|no sugar", "Low sugar", SUGAR),
    (r"low sodium|low salt", "Low sodium", HIGH_SALT),
]


def active_rules(dietary_notes: str | None) -> list[tuple[str, list[str]]]:
    if not dietary_notes:
        return []
    notes = dietary_notes.lower()
    return [(label, words) for pattern, label, words in RULES if re.search(pattern, notes)]


def check_meal(description: str, dietary_notes: str | None) -> list[str]:
    """Return human-readable conflicts, e.g. ["Vegetarian: mentions 'chicken'"]."""
    desc = description.lower()
    conflicts = []
    for label, words in active_rules(dietary_notes):
        hits = [w for w in words if re.search(rf"\b{re.escape(w)}", desc)]
        if hits:
            conflicts.append(f"{label}: mentions {', '.join(repr(h) for h in sorted(set(hits)))}")
    return conflicts
