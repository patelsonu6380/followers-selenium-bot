import json
import os
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, firestore

_APP_NAME = "gmail_firestore_backend"


def _read_env_file(path):
    values = {}
    if not path.exists():
        return values

    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        values[key] = value
    return values


def _load_local_env():
    base = Path(__file__).resolve().parent.parent
    env_paths = [
        base / "gmail work" / ".env",
        base / ".env",
    ]
    merged = {}
    for path in env_paths:
        merged.update(_read_env_file(path))
    return merged


def _env(name, local_env):
    return (os.getenv(name) or local_env.get(name) or "").strip()


def _init_firestore_app():
    try:
        return firebase_admin.get_app(_APP_NAME)
    except ValueError:
        pass

    local_env = _load_local_env()

    firebase_json = _env("FIREBASE_KEY_JSON", local_env)
    if firebase_json:
        cred = credentials.Certificate(json.loads(firebase_json))
        return firebase_admin.initialize_app(cred, name=_APP_NAME)

    project_id = _env("FIREBASE_PROJECT_ID", local_env)
    client_email = _env("FIREBASE_CLIENT_EMAIL", local_env)
    private_key = _env("FIREBASE_PRIVATE_KEY", local_env).replace("\\n", "\n")

    if project_id and client_email and "BEGIN PRIVATE KEY" in private_key:
        cred = credentials.Certificate(
            {
                "type": "service_account",
                "project_id": project_id,
                "client_email": client_email,
                "private_key": private_key,
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        )
        return firebase_admin.initialize_app(cred, name=_APP_NAME)

    fallback_key = Path(__file__).resolve().parent / "serviceAccountKey.json"
    if not fallback_key.exists():
        raise FileNotFoundError("serviceAccountKey.json not found for gmail accounts lookup")

    cred = credentials.Certificate(str(fallback_key))
    return firebase_admin.initialize_app(cred, name=_APP_NAME)


def get_refresh_token_by_email(email):
    local_env = _load_local_env()
    explicit = _env("FIREBASE_ACCOUNTS_COLLECTION", local_env)
    collections = [explicit] if explicit else []
    collections.extend(["gmail_accounts", "accounts"])

    client = firestore.client(app=_init_firestore_app())
    seen = set()

    for collection_name in collections:
        if not collection_name or collection_name in seen:
            continue
        seen.add(collection_name)

        query = (
            client.collection(collection_name)
            .where("email", "==", email)
            .limit(1)
            .stream()
        )

        for doc in query:
            data = doc.to_dict() or {}
            refresh_token = str(data.get("refreshToken") or data.get("refresh_token") or "").strip()
            if refresh_token:
                return refresh_token

    checked = ", ".join(seen) if seen else "no collection"
    raise RuntimeError(f"Refresh token not found for Gmail: {email}. Checked: {checked}")
