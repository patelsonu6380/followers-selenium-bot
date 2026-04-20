# ============================================================
# websites.py
# Firebase-backed but bot.py compatible
# ============================================================

import firebase_init
from firebase_admin import db

def _load_websites():
    ref = db.reference("websites")
    data = ref.get() or {}

    websites = []

    for site in data.values():
        if not isinstance(site, dict):
            continue

        name = site.get("name")
        login_url = site.get("login_url")

        if name and login_url:
            websites.append({
                "name": name,
                "login_url": login_url
            })

    if not websites:
        raise Exception("❌ No websites found in Firebase")

    return websites


# 🔥 EXACT SAME VARIABLE bot.py expects
WEBSITES = _load_websites()