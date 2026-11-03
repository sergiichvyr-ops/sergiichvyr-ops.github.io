#!/usr/bin/env python3
"""Upload one video to YouTube as PRIVATE (used by .github/workflows/youtube-upload.yml).

Credentials come from env vars only: YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN.
Nothing secret is ever printed.

Privacy is hard-coded to "private" and selfDeclaredMadeForKids to False on purpose:
the channel owner flips videos to Public by hand in YouTube Studio.
"""
import argparse
import os
import sys
import time

TITLE_MAX_CHARS = 100
DESCRIPTION_MAX_BYTES = 5000
TAGS_MAX_CHARS = 500
CATEGORY_GAMING = "20"
TOKEN_URI = "https://oauth2.googleapis.com/token"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
RETRY_STATUS = {500, 502, 503, 504}
MAX_RETRIES = 8


def fail(msg):
    print(f"::error::{msg}", file=sys.stderr)
    sys.exit(1)


def parse_tags(raw):
    tags = [t.strip() for t in (raw or "").split(",") if t.strip()]
    # YouTube counts a tag containing spaces as if wrapped in quotes, plus commas between tags.
    total = sum(len(t) + (2 if " " in t else 0) for t in tags) + max(len(tags) - 1, 0)
    return tags, total


def validate(title, description, tags_raw):
    errors = []
    title = (title or "").strip()
    if not title:
        errors.append("title is empty.")
    if len(title) > TITLE_MAX_CHARS:
        errors.append(f"title is {len(title)} characters; YouTube allows at most {TITLE_MAX_CHARS}.")
    desc_bytes = len((description or "").encode("utf-8"))
    if desc_bytes > DESCRIPTION_MAX_BYTES:
        errors.append(f"description is {desc_bytes} bytes; YouTube allows at most {DESCRIPTION_MAX_BYTES}.")
    for name, value in (("title", title), ("description", description or "")):
        if "<" in value or ">" in value:
            errors.append(f"{name} contains '<' or '>', which YouTube rejects.")
    tags, tags_len = parse_tags(tags_raw)
    if tags_len > TAGS_MAX_CHARS:
        errors.append(f"tags total {tags_len} characters; YouTube allows at most {TAGS_MAX_CHARS}.")
    if errors:
        fail("Invalid metadata: " + " ".join(errors))
    return title, description or "", tags


def summary(lines):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")


def build_service():
    missing = [k for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN") if not os.environ.get(k)]
    if missing:
        fail("Missing repository secret(s): " + ", ".join(missing)
             + ". See tools/youtube/README.md (or run with dry_run=true to test without credentials).")
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials(
        token=None,
        refresh_token=os.environ["YT_REFRESH_TOKEN"],
        client_id=os.environ["YT_CLIENT_ID"],
        client_secret=os.environ["YT_CLIENT_SECRET"],
        token_uri=TOKEN_URI,
        scopes=SCOPES,
    )
    try:
        creds.refresh(Request())
    except RefreshError as exc:
        text = str(exc)
        if "invalid_grant" in text:
            fail("Google rejected YT_REFRESH_TOKEN (invalid_grant): the refresh token expired or was revoked. "
                 "Common causes: OAuth consent screen still in 'Testing' (tokens expire after 7 days), "
                 "you removed the app's access in your Google account, or the password changed. "
                 "Re-run tools/youtube/mint_refresh_token.py and update the YT_REFRESH_TOKEN secret.")
        if "invalid_client" in text or "unauthorized_client" in text:
            fail("Google rejected YT_CLIENT_ID / YT_CLIENT_SECRET (invalid_client). Check both secrets come from "
                 "the same Desktop OAuth client that minted the refresh token.")
        fail("Could not get a Google access token (" + exc.__class__.__name__ + "). Check the YT_* secrets.")
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def http_error_reason(exc):
    try:
        import json
        data = json.loads(exc.content.decode("utf-8"))
        errs = data.get("error", {}).get("errors", [])
        return (errs[0].get("reason") if errs else "") or "", data.get("error", {}).get("message", "")
    except Exception:  # noqa: BLE001
        return "", ""


def upload(path, title, description, tags):
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    youtube = build_service()
    body = {
        "snippet": {"title": title, "description": description, "tags": tags, "categoryId": CATEGORY_GAMING},
        "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False},
    }
    if not tags:
        del body["snippet"]["tags"]
    media = MediaFileUpload(path, mimetype="video/*", chunksize=8 * 1024 * 1024, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media, notifySubscribers=False)

    response, retries = None, 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                print(f"Uploaded {int(status.progress() * 100)}%")
        except HttpError as exc:
            reason, message = http_error_reason(exc)
            code = exc.resp.status
            if reason in ("quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded"):
                fail(f"YouTube API quota exceeded ({reason}). The videos.insert quota resets at midnight "
                     "Pacific Time; try again later or request more quota in the Google Cloud console.")
            if reason == "uploadLimitExceeded":
                fail("YouTube says this channel hit its upload limit (uploadLimitExceeded). Try again in 24h.")
            if code == 401 or reason in ("authError", "insufficientPermissions"):
                fail(f"YouTube refused the credentials ({reason or code}). The refresh token must be minted with "
                     "the youtube.upload scope by the account that manages the channel.")
            if code in RETRY_STATUS and retries < MAX_RETRIES:
                retries += 1
                wait = min(2 ** retries, 60)
                print(f"Transient HTTP {code}; retry {retries}/{MAX_RETRIES} in {wait}s")
                time.sleep(wait)
                continue
            fail(f"YouTube upload failed: HTTP {code} {reason} {message}".strip())
        except (ConnectionError, TimeoutError, OSError) as exc:
            if retries < MAX_RETRIES:
                retries += 1
                wait = min(2 ** retries, 60)
                print(f"Network error ({exc.__class__.__name__}); retry {retries}/{MAX_RETRIES} in {wait}s")
                time.sleep(wait)
                continue
            raise

    video_id = response["id"]
    privacy = response.get("status", {}).get("privacyStatus", "?")
    url = f"https://youtu.be/{video_id}"
    studio = f"https://studio.youtube.com/video/{video_id}/edit"
    print(f"Uploaded video id {video_id} (privacy: {privacy})")
    print(f"Watch: {url}")
    print(f"Studio: {studio}")
    summary([
        "## YouTube upload (private)",
        "",
        f"- Title: {title}",
        f"- Privacy: `{privacy}`",
        f"- Video: {url}",
        f"- YouTube Studio: {studio}",
        "",
        "Flip it to Public in YouTube Studio when ready.",
    ])
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"video_id={video_id}\nvideo_url={url}\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--description", default="")
    ap.add_argument("--tags", default="", help="comma-separated")
    ap.add_argument("--dry-run", action="store_true", help="validate only, skip upload")
    args = ap.parse_args()

    if not os.path.isfile(args.file) or os.path.getsize(args.file) == 0:
        fail(f"Video file {args.file!r} is missing or empty.")
    # workflow_dispatch inputs are single-line; a typed "\n" becomes a real line break.
    description = (args.description or "").replace("\\n", "\n")
    title, description, tags = validate(args.title, description, args.tags)
    size = os.path.getsize(args.file)
    print(f"Metadata OK: title {len(title)} chars, description {len(description.encode('utf-8'))} bytes, "
          f"{len(tags)} tag(s); file {size} bytes ({size / 1024 / 1024:.2f} MiB)")

    if args.dry_run:
        print("Dry run: skipping upload.")
        summary([
            "## YouTube upload: DRY RUN (nothing uploaded)",
            "",
            f"- Title: {title} ({len(title)}/{TITLE_MAX_CHARS} chars)",
            f"- Description: {len(description.encode('utf-8'))}/{DESCRIPTION_MAX_BYTES} bytes",
            f"- Tags: {', '.join(tags) or '(none)'}",
            f"- File size: {size} bytes ({size / 1024 / 1024:.2f} MiB)",
            "- Would upload as: `private`, category 20 (Gaming), made for kids: false",
        ])
        return
    upload(args.file, title, description, tags)


if __name__ == "__main__":
    main()
