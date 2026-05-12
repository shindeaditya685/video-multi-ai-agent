"""
Upload Agent

Uploads the final video and thumbnail to YouTube when OAuth credentials are
available. The local reviewed workflow keeps this optional.
"""

from __future__ import annotations

import os
import pickle
from pathlib import Path

from core.config import PipelineState, YOUTUBE_CATEGORY_ID, YOUTUBE_CLIENT_SECRETS, YOUTUBE_PRIVACY

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_FILE = "youtube_token.pickle"
API_SERVICE = "youtube"
API_VERSION = "v3"
CHUNK_SIZE = 1024 * 1024 * 5


def _get_youtube_service():
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(YOUTUBE_CLIENT_SECRETS, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)

    return build(API_SERVICE, API_VERSION, credentials=creds)


def upload_video(youtube, state: PipelineState) -> str:
    from googleapiclient.http import MediaFileUpload

    body = {
        "snippet": {
            "title": state.title[:100],
            "description": (
                f"{state.hook}\n\n"
                f"{state.story[:4000]}\n\n"
                "#TrueCrime #Documentary #Crime"
            ),
            "tags": ["true crime", "documentary", "crime", "mystery", state.topic],
            "categoryId": YOUTUBE_CATEGORY_ID,
        },
        "status": {
            "privacyStatus": YOUTUBE_PRIVACY,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        str(state.captioned_path),
        mimetype="video/mp4",
        chunksize=CHUNK_SIZE,
        resumable=True,
    )

    print(f"    Uploading video ({state.captioned_path.stat().st_size / 1_048_576:.1f} MB)...")
    request = youtube.videos().insert(part=",".join(body.keys()), body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            print(f"    Upload progress: {pct}%", end="\r")

    video_id = response["id"]
    return f"https://www.youtube.com/watch?v={video_id}"


def upload_thumbnail(youtube, video_url: str, thumbnail_path: Path):
    from googleapiclient.http import MediaFileUpload

    video_id = video_url.split("v=")[-1]
    media = MediaFileUpload(str(thumbnail_path), mimetype="image/png")
    youtube.thumbnails().set(videoId=video_id, media_body=media).execute()
    print("    Thumbnail uploaded.")


def run(state: PipelineState, skip_upload: bool = False) -> PipelineState:
    print("\n[Upload] Upload Agent - posting to YouTube...")
    state.status = "uploading"
    state.progress = 98

    if skip_upload:
        print("    Upload skipped (skip_upload=True). Video ready locally.")
        state.youtube_url = ""
        state.progress = 100
        return state

    if not os.path.exists(YOUTUBE_CLIENT_SECRETS):
        print(
            f"    client_secrets.json not found at '{YOUTUBE_CLIENT_SECRETS}'.\n"
            "    Upload skipped. See agents/10_upload_agent.py for setup instructions.\n"
            f"    Your video is ready at: {state.captioned_path}"
        )
        state.progress = 100
        return state

    try:
        youtube = _get_youtube_service()
        state.youtube_url = upload_video(youtube, state)
        print(f"\n    Uploaded: {state.youtube_url}")

        if state.thumbnail_path and state.thumbnail_path.exists():
            upload_thumbnail(youtube, state.youtube_url, state.thumbnail_path)

    except Exception as e:
        state.errors.append(f"Upload failed: {e}")
        print(f"    Upload error: {e}")

    state.progress = 100
    state.status = "done"
    return state
