# firebase_init.py
import firebase_admin
from firebase_admin import credentials, db
import json
import os

# Prevent multiple initializations
if not firebase_admin._apps:
    firebase_json = os.environ.get("FIREBASE_KEY_JSON")

    if not firebase_json:
        raise Exception("FIREBASE_KEY_JSON env var not set")

    cred_dict = json.loads(firebase_json)
    cred = credentials.Certificate(cred_dict)

    firebase_admin.initialize_app(cred, {
        "databaseURL": "https://reseller-panel-d376c-default-rtdb.firebaseio.com/"
    })