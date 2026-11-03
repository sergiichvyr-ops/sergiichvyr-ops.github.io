#!/usr/bin/env python3
"""One-time: mint a YouTube upload refresh token on YOUR OWN computer.

Usage:
    python3 -m venv .venv && . .venv/bin/activate
    pip install google-auth-oauthlib
    python3 mint_refresh_token.py path/to/client_secret_XXXX.json

A browser opens; sign in with the Google account that owns/manages @ProminentGame
and pick that channel. Only the refresh token is printed (to stdout). Paste it into
the YT_REFRESH_TOKEN repository secret, then delete the client_secret JSON or keep it
somewhere private. Never commit either.
"""
import contextlib
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def main():
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    flow = InstalledAppFlow.from_client_secrets_file(sys.argv[1], scopes=SCOPES)
    # Keep stdout clean: the sign-in URL / messages go to stderr, only the token goes to stdout.
    with contextlib.redirect_stdout(sys.stderr):
        creds = flow.run_local_server(
            port=0,
            access_type="offline",
            prompt="consent",
            authorization_prompt_message="Opening your browser to sign in. If it doesn't open, visit:\n{url}\n",
            success_message="Done. You can close this tab and return to the terminal.",
            open_browser=True,
        )
    if not creds.refresh_token:
        print("No refresh token returned. Remove the app's access at https://myaccount.google.com/permissions "
              "and run again.", file=sys.stderr)
        sys.exit(1)
    print(creds.refresh_token)


if __name__ == "__main__":
    main()
