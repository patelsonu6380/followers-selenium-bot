# ============================================================
# accounts.py
# DO NOT change bot.py
# Logic:
# - Login fail count tracked in Firebase
# - 15+ fails => permanentBlocked = true
# - Permanently blocked IDs are NEVER selected
# ============================================================

import firebase_init
import time
import random
from firebase_admin import db

# ================= CONFIG =================
COOLDOWN_SECONDS = 90 * 60      # 1.5 hours temporary lock
MAX_ACCOUNTS = 1               # bot max 1 accounts
MIN_ACCOUNTS = 1               # at least 1 required
MAX_FAILS = 15                 # 🔥 permanent block limit


# ============================================================
# 🔒 TEMPORARY LOCK (used by bot)
# ============================================================
def _try_lock_account(acc_id):
    ref = db.reference(f"accounts/{acc_id}")

    def txn(current):
        if not current:
            return None

        # ❌ permanently blocked → never lock
        if current.get("permanentBlocked") is True:
            return None

        now = int(time.time())

        # already locked
        if current.get("lockedUntil", 0) > now:
            return None

        current["lockedUntil"] = now + COOLDOWN_SECONDS
        current["lastUsed"] = now
        return current

    return ref.transaction(txn) is not None


# ============================================================
# 🔥 LOGIN FAIL COUNTER (call from outside bot.py)
# ============================================================
def register_login_fail(acc_id):
    """
    Call this when login fails.
    After 15 fails → permanentBlocked = true
    """

    ref = db.reference(f"accounts/{acc_id}")

    def txn(current):
        if not current:
            return None

        fails = current.get("failCount", 0) + 1
        current["failCount"] = fails

        if fails >= MAX_FAILS:
            current["permanentBlocked"] = True
            current["lockedUntil"] = 9999999999  # extra safety

        return current

    ref.transaction(txn)


# ============================================================
# ✅ LOGIN SUCCESS RESET
# ============================================================
def register_login_success(acc_id):
    ref = db.reference(f"accounts/{acc_id}")

    def txn(current):
        if not current:
            return None

        current["failCount"] = 0
        return current

    ref.transaction(txn)


# ============================================================
# 🎯 ACCOUNT SELECTION (bot.py uses this)
# ============================================================
def _select_accounts():
    ref = db.reference("accounts")
    data = ref.get() or {}
    now = int(time.time())

    # 🔹 only usable accounts
    free_accounts = []

    for acc_id, acc in data.items():
        if acc.get("permanentBlocked") is True:
            continue

        if acc.get("lockedUntil", 0) > now:
            continue

        free_accounts.append((acc_id, acc))

    if len(free_accounts) < MIN_ACCOUNTS:
        raise Exception("❌ Not enough free accounts (others blocked)")

    random.shuffle(free_accounts)

    selected = []

    for acc_id, acc in free_accounts:
        if _try_lock_account(acc_id):
            selected.append({
                "user": acc["username"],
                "pass": acc["password"],
                "_id": acc_id   # optional (for fail tracking)
            })

        if len(selected) == min(MAX_ACCOUNTS, len(free_accounts)):
            break

    if len(selected) < MIN_ACCOUNTS:
        raise Exception("❌ Could not lock required accounts")

    return selected


# ============================================================
# 🔥 bot.py IMPORTS THIS
# ============================================================

LOGIN_ACCOUNTS = _select_accounts()                 
