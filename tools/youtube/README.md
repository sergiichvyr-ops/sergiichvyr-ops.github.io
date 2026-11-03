# YouTube upload (private) for Tilecharm and Glidevane

The workflow `.github/workflows/youtube-upload.yml` (Actions tab > **YouTube upload (private)** > **Run workflow**)
takes one video from `sergiichvyr-ops/tilecharm` or `sergiichvyr-ops/glidevane`
(e.g. `store/video/tilecharm-promo-15s.mp4`) and uploads it to **@ProminentGame** as **private**,
category Gaming (20), made for kids = false, subscribers not notified. You flip it to Public in YouTube Studio.
The run summary shows the `https://youtu.be/<id>` link and the YouTube Studio edit link.

Inputs: `game`, `video_path`, `ref` (default `main`), `title` (max 100 chars), `description`
(max 5000 bytes; type `\n` for a line break), `tags` (comma-separated), `dry_run`.
`dry_run = true` fetches the video, validates the metadata and prints the size without uploading,
so it needs `GAME_REPO_TOKEN` but no YouTube secrets.

## One-time setup (about 10 minutes)

1. **Google Cloud project.** Go to https://console.cloud.google.com/projectcreate and create a project
   (e.g. "ProminentGame YouTube upload"). No billing account is needed.
2. **Enable the API.** APIs & Services > Library > search "YouTube Data API v3" > **Enable**
   (https://console.cloud.google.com/apis/library/youtube.googleapis.com).
3. **OAuth consent screen** (Google Auth Platform > Branding / Audience / Data access):
   User type **External**; app name (e.g. "ProminentGame uploader"); your email as support and developer
   contact; under Data access add the scope `https://www.googleapis.com/auth/youtube.upload`; under Audience
   add yourself as a test user. Then on Audience click **Publish app** to move it to **In production**.
   It stays unverified, and you'll see a "Google hasn't verified this app" warning when you sign in
   (click Advanced > Go to ... ); that's fine because you're the only user. Publish it because
   in "Testing" status, refresh tokens expire after 7 days.
4. **OAuth client.** Google Auth Platform > Clients > **Create client** > Application type **Desktop app** >
   Create > **Download JSON** (`client_secret_....json`). Keep it private and never commit it.
5. **Mint the refresh token on your own computer** (not in CI):
   ```sh
   python3 -m venv .venv && . .venv/bin/activate
   pip install -r tools/youtube/requirements.txt   # or just: pip install google-auth-oauthlib
   python3 tools/youtube/mint_refresh_token.py ~/Downloads/client_secret_XXXX.json
   ```
   A browser opens. Sign in with the Google account that owns or manages **@ProminentGame**, and when asked
   to choose an account or channel, **pick the @ProminentGame channel** (not a personal channel). Allow
   access. The script prints only the refresh token.
6. **Add the secrets** to `sergiichvyr-ops/sergiichvyr-ops.github.io` (Settings > Secrets and variables >
   Actions > New repository secret, or with the CLI, which prompts so nothing lands in shell history):
   ```sh
   R=sergiichvyr-ops/sergiichvyr-ops.github.io
   gh secret set YT_CLIENT_ID     -R $R   # "client_id" from the JSON
   gh secret set YT_CLIENT_SECRET -R $R   # "client_secret" from the JSON
   gh secret set YT_REFRESH_TOKEN -R $R   # output of step 5
   ```
7. **Game repo token (needed: both game repos are private).** https://github.com/settings/personal-access-tokens/new >
   Fine-grained token, resource owner `sergiichvyr-ops`, expiration of your choice, **Only select repositories**:
   `tilecharm` and `glidevane`, Repository permissions: **Contents: Read-only** (Metadata: Read-only is added
   automatically). Generate, then `gh secret set GAME_REPO_TOKEN -R $R`. If a game repo is ever made
   public, the workflow can read it without this token. If the token is missing or expired, the run fails
   with a message saying so.
8. **Test.** Run the workflow with `dry_run = true`, then for real with a short title. Check the summary
   link and YouTube Studio.

## Quota and limits

- Per Google's current Quota Calculator (https://developers.google.com/youtube/v3/determine_quota_cost),
  `videos.insert` has its **own quota bucket: 100 uploads per day by default** (1 unit per call), separate
  from the 10,000 units/day for other methods. This changed in 2025–2026; the old "~1,600 units per upload, about
  6 uploads/day" rule no longer applies. Quotas reset at midnight Pacific Time. YouTube may also cap
  uploads per channel per day (`uploadLimitExceeded`).
- The video is fetched through the GitHub contents API, which serves files up to 100 MB. Git LFS files
  are handled (the workflow downloads the LFS object).

## Unverified API project and private videos

Before Nov 2, 2026, uploads from unverified API projects created after July 28, 2020 were locked
to private until the project passed YouTube's API compliance audit. Google reversed that.
The `videos.insert` docs (https://developers.google.com/youtube/v3/docs/videos/insert) now say:
"Videos uploaded from unverified API projects are not restricted to private viewing mode." and the
revision history (https://developers.google.com/youtube/v3/revision_history, November 2, 2026) says:
"Videos uploaded through the videos.insert method from unverified API projects are no longer restricted
to private viewing mode." So you can switch these uploads to Public yourself in YouTube Studio
without an audit. If Google brings the lock back, or you need more quota, use the audit / quota
extension form: https://support.google.com/youtube/contact/yt_api_form

## Troubleshooting

- `invalid_grant`: the refresh token expired or was revoked (app still in Testing, access removed at
  https://myaccount.google.com/permissions, or password change). Redo step 5 and update `YT_REFRESH_TOKEN`.
- `invalid_client`: `YT_CLIENT_ID`/`YT_CLIENT_SECRET` don't match the client that minted the token.
- `quotaExceeded`: daily quota used up; wait for the Pacific-midnight reset.
- Video went to the wrong channel: re-mint (step 5) and pick @ProminentGame on the channel chooser.
