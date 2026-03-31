"""
Firebase authentication helpers for backend token verification.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

import firebase_admin
from fastapi import Header, HTTPException
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials


FIREBASE_WEB_CONFIG_KEYS = {
    "apiKey": "FIREBASE_API_KEY",
    "authDomain": "FIREBASE_AUTH_DOMAIN",
    "projectId": "FIREBASE_PROJECT_ID",
    "storageBucket": "FIREBASE_STORAGE_BUCKET",
    "messagingSenderId": "FIREBASE_MESSAGING_SENDER_ID",
    "appId": "FIREBASE_APP_ID",
    "measurementId": "FIREBASE_MEASUREMENT_ID",
}


class FirebaseConfigurationError(RuntimeError):
    """Raised when Firebase credentials are missing or invalid."""


BACKEND_DIR = Path(__file__).resolve().parent


def _parse_inline_json(candidate: str) -> Optional[dict]:
    value = candidate.strip()
    if not value.startswith("{"):
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise FirebaseConfigurationError(
            "FIREBASE_ADMIN_CREDENTIALS contains invalid JSON."
        ) from exc
    return parsed if isinstance(parsed, dict) else None


def _resolve_credentials_path(candidate: str) -> Optional[Path]:
    value = candidate.strip()
    if not value or value.startswith("{"):
        return None
    path = Path(value)
    if not path.is_absolute():
        path = (BACKEND_DIR / path).resolve()
    return path if path.exists() else None


def _get_admin_credentials_info() -> Optional[dict]:
    candidates = [
        os.getenv("FIREBASE_ADMIN_CREDENTIALS", ""),
        os.getenv("GOOGLE_APPLICATION_CREDENTIALS", ""),
    ]

    for candidate in candidates:
        parsed = _parse_inline_json(candidate)
        if parsed:
            return parsed
    return None


def get_firebase_web_config() -> dict:
    config = {
        key: os.getenv(env_name, "").strip()
        for key, env_name in FIREBASE_WEB_CONFIG_KEYS.items()
    }
    required_keys = ("apiKey", "authDomain", "projectId", "appId")
    configured = all(config.get(key) for key in required_keys)
    return {
        "configured": configured,
        "config": config,
        "message": (
            None
            if configured
            else "Firebase web configuration is incomplete. Set the FIREBASE_* variables first."
        ),
    }


def _get_admin_credentials_path() -> Optional[Path]:
    candidates = [
        os.getenv("FIREBASE_ADMIN_CREDENTIALS", "").strip(),
        os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip(),
    ]

    for candidate in candidates:
        path = _resolve_credentials_path(candidate)
        if path:
            return path
    return None


def get_firebase_admin_app():
    try:
        return firebase_admin.get_app()
    except ValueError:
        credentials_info = _get_admin_credentials_info()
        if credentials_info:
            credential = credentials.Certificate(credentials_info)
            return firebase_admin.initialize_app(credential)

        credentials_path = _get_admin_credentials_path()
        if not credentials_path:
            raise FirebaseConfigurationError(
                "Firebase Admin credentials are not configured. "
                "Set FIREBASE_ADMIN_CREDENTIALS or GOOGLE_APPLICATION_CREDENTIALS."
            )
        credential = credentials.Certificate(str(credentials_path))
        return firebase_admin.initialize_app(credential)


def verify_firebase_token(token: str) -> dict:
    try:
        app = get_firebase_admin_app()
        return firebase_auth.verify_id_token(token, app=app)
    except FirebaseConfigurationError:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Invalid Firebase token: {exc}") from exc


def _parse_bearer_token(authorization: Optional[str]) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise HTTPException(status_code=401, detail="Authorization header must use Bearer token")

    return parts[1].strip()


async def get_current_user(authorization: Optional[str] = Header(default=None)) -> dict:
    token = _parse_bearer_token(authorization)

    try:
        decoded = verify_firebase_token(token)
    except FirebaseConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "uid": decoded["uid"],
        "email": decoded.get("email"),
        "name": decoded.get("name"),
        "email_verified": decoded.get("email_verified", False),
    }


