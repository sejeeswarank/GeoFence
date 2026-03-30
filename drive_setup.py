"""
One-time Google Drive OAuth setup for GeoFence app storage.
"""

from __future__ import annotations

import os
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

from drive_storage import DRIVE_SCOPES


def main() -> None:
    credentials_file = Path(
        os.getenv("GOOGLE_DRIVE_OAUTH_CREDENTIALS_FILE", "google-drive-oauth-client.json")
    )
    token_file = Path(os.getenv("GOOGLE_DRIVE_TOKEN_FILE", "google-drive-token.json"))

    if not credentials_file.exists():
        raise FileNotFoundError(
            f"Missing OAuth client file at {credentials_file}. "
            "Download it from Google Cloud Console first."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(credentials_file), DRIVE_SCOPES)
    creds = flow.run_local_server(port=0)
    token_file.write_text(creds.to_json(), encoding="utf-8")

    print(f"Saved Google Drive token to {token_file}")


if __name__ == "__main__":
    main()
