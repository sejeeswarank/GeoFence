"""
Google Drive-backed JSON persistence for authenticated users.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload


DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.appdata"]


class DriveConfigurationError(RuntimeError):
    """Raised when Google Drive credentials are missing or invalid."""


class DriveStorage:
    def __init__(self) -> None:
        self.credentials_file = Path(
            os.getenv("GOOGLE_DRIVE_OAUTH_CREDENTIALS_FILE", "google-drive-oauth-client.json")
        )
        self.token_file = Path(
            os.getenv("GOOGLE_DRIVE_TOKEN_FILE", "google-drive-token.json")
        )

    def status(self) -> dict:
        return {
            "configured": self.credentials_file.exists() and self.token_file.exists(),
            "credentials_file": self.credentials_file.name,
            "token_file": self.token_file.name,
            "message": (
                "Google Drive is ready."
                if self.credentials_file.exists() and self.token_file.exists()
                else (
                    "Google Drive is not configured yet. Run drive_setup.py after creating "
                    "an OAuth client file."
                )
            ),
        }

    def _load_credentials(self) -> Credentials:
        if not self.credentials_file.exists():
            raise DriveConfigurationError(
                f"Missing Google Drive OAuth credentials file: {self.credentials_file}"
            )
        if not self.token_file.exists():
            raise DriveConfigurationError(
                f"Missing Google Drive token file: {self.token_file}. Run drive_setup.py first."
            )

        credentials = Credentials.from_authorized_user_file(str(self.token_file), DRIVE_SCOPES)
        if not credentials.valid:
            if credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
                self.token_file.write_text(credentials.to_json(), encoding="utf-8")
            else:
                raise DriveConfigurationError(
                    "Google Drive token is invalid or expired without a refresh token. "
                    "Run drive_setup.py again."
                )

        return credentials

    def _build_service(self):
        credentials = self._load_credentials()
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
        service = self._build_service()
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
        service = self._build_service()
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
