# firebase_init.py
import firebase_admin
from firebase_admin import credentials, db
import json
import os
from pathlib import Path

def init_firebase():
    if firebase_admin._apps:
        return

    firebase_json = os.getenv("FIREBASE_KEY_JSON")

    if firebase_json:
        # Server / CI
        cred_dict = json.loads(firebase_json)
        cred = credentials.Certificate(cred_dict)
    else:
        # ✅ VS Code / Local
        base_dir = Path(__file__).resolve().parent
        key_path = base_dir / "serviceAccountKey.json"

        if not key_path.exists():
            raise Exception("❌ serviceAccountKey.json not found")

        cred = credentials.Certificate(str(key_path))

    firebase_admin.initialize_app(cred, {
        "databaseURL": "https://reseller-panel-d376c-default-rtdb.firebaseio.com/"
    })

# 🔥 IMPORTANT: auto init for VS Code
init_firebase()
