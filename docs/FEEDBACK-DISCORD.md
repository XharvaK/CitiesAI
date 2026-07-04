# Discord feedback webhook

CitiesAI can post in-app **Feedback** submissions to a Discord channel. A local JSON copy is always saved under `%APPDATA%\CitiesAI\feedback\`.

## 1. Create the webhook in Discord

1. Open your Discord server (create one for beta if you do not have one yet).
2. Create a channel, e.g. `#citiesai-feedback`.
3. **Edit channel** → **Integrations** → **Webhooks** → **Create Webhook** (or **New Webhook**).
4. Name it `CitiesAI Feedback`, pick the channel, **Save**.
5. Click **Copy Webhook URL**. It looks like:
   `https://discord.com/api/webhooks/1234567890123456789/abcdefghijklmnopqrstuvwxyz...`

Treat this URL like a password. Anyone with it can post to your channel. Do not commit it to git.

## 2. Store it locally for builds

```powershell
cd C:\Users\Xharv\Projects\CitiesAI
copy packaging\secrets.local.env.example packaging\secrets.local.env
notepad packaging\secrets.local.env
```

Paste your webhook URL on the `CITIESAI_DISCORD_WEBHOOK=` line and save.

`packaging/secrets.local.env` is gitignored.

## 3. Build the installer

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build-release.ps1
```

The build script writes `packaging/bundled/feedback_webhook.url` and PyInstaller bundles it into `CitiesAI.exe`.

You should see:

`Bundled Discord webhook for release: ...\packaging\bundled\feedback_webhook.url`

## 4. Ship and test

1. Upload the new installer to GitHub Releases (or share locally).
2. Install/run CitiesAI.
3. Open **Feedback**, send a test message with **Contact** filled in.
4. Check `#citiesai-feedback` for an embed.

Success message in the app: *"Thanks! Your feedback was sent to the beta channel."*

## Dev without rebuilding

For `uv run citiesai gui` on your machine only:

```powershell
$env:CITIESAI_DISCORD_WEBHOOK = "https://discord.com/api/webhooks/..."
uv run citiesai gui
```

## If the webhook leaks

1. Discord → channel webhooks → delete the old webhook.
2. Create a new one.
3. Update `packaging/secrets.local.env` and rebuild.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| App says "Saved locally" | Shipped build was made without `secrets.local.env`. Rebuild after step 2. |
| Discord shows nothing, local file exists | Firewall or bad URL. Check app toast for "Could not reach Discord". |
| SmartScreen blocks installer | Unrelated to webhooks; Run anyway or rebuild signed later. |
