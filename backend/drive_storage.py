"""
Google Drive-backed JSON persistence for authenticated users.
"""

from __future__ import annotations

import io
import json
import os
import secrets
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload


DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.appdata"]


class DriveConfigurationError(RuntimeError):
    """Raised when Google Drive credentials are missing or invalid."""


class DriveStorage:
    def __init__(self) -> None:
        self.base_dir = Path(__file__).resolve().parent
        self.credentials_file = self._resolve_path(
            os.getenv("GOOGLE_DRIVE_OAUTH_CREDENTIALS_FILE", "google-drive-oauth-client.json")
        )
        self.legacy_token_file = self._resolve_path(
            os.getenv("GOOGLE_DRIVE_TOKEN_FILE", "google-drive-token.json")
        )
        self.token_dir = self._resolve_path(
            os.getenv("GOOGLE_DRIVE_TOKEN_DIR", str(self.base_dir / "drive_tokens"))
        )

    def _resolve_path(self, value: str) -> Path:
        path = Path(value)
        return path if path.is_absolute() else (self.base_dir / path).resolve()

    @staticmethod
    def _safe_uid(uid: str) -> str:
        return "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in uid).strip("_") or "user"

    def _token_file_for_uid(self, uid: str) -> Path:
        return self.token_dir / f"{self._safe_uid(uid)}.json"

    def status(self, uid: str) -> dict:
        has_credentials = self.credentials_file.exists()
        token_file = self._token_file_for_uid(uid)
        has_token = has_credentials and token_file.exists()
        has_legacy_token = has_credentials and self.legacy_token_file.exists()
        if has_token:
            message = "Google Drive is ready for this user."
        elif has_legacy_token:
            message = "A legacy shared Drive connection exists. Reconnect Drive to link it to this user."
        elif has_credentials:
            message = "Google Drive OAuth client found but not yet authorized. Click Connect to Drive."
        else:
            message = "Google Drive OAuth client file is missing. Upload it first."
        return {
            "configured": has_token,
            "has_credentials": has_credentials,
            "credentials_file": self.credentials_file.name,
            "token_file": token_file.name,
            "token_directory": str(self.token_dir),
            "legacy_token_detected": has_legacy_token,
            "message": message,
        }

    def build_auth_url(self, redirect_uri: str, state: str) -> tuple[str, str]:
        """Build a Google OAuth consent URL for the browser flow."""
        if not self.credentials_file.exists():
            raise DriveConfigurationError(
                "Missing Google Drive OAuth client file. Upload it before connecting."
            )
        flow = Flow.from_client_secrets_file(
            str(self.credentials_file),
            scopes=DRIVE_SCOPES,
            redirect_uri=redirect_uri,
        )
        code_verifier = secrets.token_urlsafe(72)
        flow.code_verifier = code_verifier
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            prompt="consent",
            state=state,
        )
        return auth_url, code_verifier

    def exchange_code(self, code: str, redirect_uri: str, uid: str, code_verifier: str) -> None:
        """Exchange the OAuth authorization code for tokens and save them."""
        if not self.credentials_file.exists():
            raise DriveConfigurationError(
                "Missing Google Drive OAuth client file."
            )
        flow = Flow.from_client_secrets_file(
            str(self.credentials_file),
            scopes=DRIVE_SCOPES,
            redirect_uri=redirect_uri,
        )
        flow.code_verifier = code_verifier
        try:
            flow.fetch_token(code=code)
        except Exception as exc:
            raise DriveConfigurationError(f"Unable to complete Google Drive sign-in: {exc}") from exc
        credentials = flow.credentials
        token_file = self._token_file_for_uid(uid)
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(credentials.to_json(), encoding="utf-8")

    def _load_credentials(self, uid: str) -> Credentials:
        if not self.credentials_file.exists():
            raise DriveConfigurationError(
                f"Missing Google Drive OAuth credentials file: {self.credentials_file}"
            )

        token_file = self._token_file_for_uid(uid)
        if not token_file.exists():
            if self.legacy_token_file.exists():
                raise DriveConfigurationError(
                    "A legacy shared Drive token was found, but this user has not connected their own Drive yet. "
                    "Use Connect to Drive from the Account page."
                )
            raise DriveConfigurationError(
                f"Missing Google Drive token file for this user: {token_file.name}. "
                "Use Connect to Drive from the Account page."
            )

        credentials = Credentials.from_authorized_user_file(str(token_file), DRIVE_SCOPES)
        if not credentials.valid:
            if credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
                token_file.write_text(credentials.to_json(), encoding="utf-8")
            else:
                raise DriveConfigurationError(
                    "Google Drive token is invalid or expired without a refresh token. "
                    "Use Connect to Drive from the Account page."
                )

        return credentials

    def _build_service(self, uid: str):
        credentials = self._load_credentials(uid)
        return build("drive", "v3", credentials=credentials, cache_discovery=False)

    @staticmethod
    def _snapshot_name(uid: str) -> str:
        return f"geofence-user-{uid}.json"

    def _find_snapshot_id(self, service, uid: str) -> Optional[str]:
        response = service.files().list(
            spaces="appDataFolder",
            fields="files(id, name)",
            q=(
                f"name = '{self._snapshot_name(uid)}' "
                "and 'appDataFolder' in parents and trashed = false"
            ),
        ).execute()
        files = response.get("files", [])
        return files[0]["id"] if files else None

    def save_user_snapshot(self, uid: str, payload: dict) -> dict:
        service = self._build_service(uid)
        payload_bytes = json.dumps(payload, indent=2).encode("utf-8")
        media = MediaIoBaseUpload(io.BytesIO(payload_bytes), mimetype="application/json", resumable=False)
        existing_file_id = self._find_snapshot_id(service, uid)

        if existing_file_id:
            file_metadata = {"name": self._snapshot_name(uid)}
            result = service.files().update(
                fileId=existing_file_id,
                body=file_metadata,
                media_body=media,
                fields="id, name, modifiedTime",
            ).execute()
        else:
            file_metadata = {
                "name": self._snapshot_name(uid),
                "parents": ["appDataFolder"],
            }
            result = service.files().create(
                body=file_metadata,
                media_body=media,
                fields="id, name, modifiedTime",
            ).execute()

        return result

    def load_user_snapshot(self, uid: str) -> Optional[dict]:
        service = self._build_service(uid)
        file_id = self._find_snapshot_id(service, uid)
        if not file_id:
            return None

        request = service.files().get_media(fileId=file_id)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)

        done = False
        while not done:
            _, done = downloader.next_chunk()

        buffer.seek(0)
        return json.loads(buffer.read().decode("utf-8"))


