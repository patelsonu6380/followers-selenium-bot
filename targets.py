# ============================================================
# targets.py
# Firebase-backed but bot.py compatible
# ============================================================

import firebase_init
from firebase_admin import db

def _load_targets():
    ref = db.reference("targets")
    data = ref.get() or {}

    targets = []

    # Firebase values simple string hain
    for v in data.values():
        if isinstance(v, str) and v.strip():
            targets.append(v.strip())

    if not targets:
        raise Exception("❌ No targets found in Firebase")

    return targets


# 🔥 EXACT SAME VARIABLE bot.py expects
TARGET_USERS = _load_targets()