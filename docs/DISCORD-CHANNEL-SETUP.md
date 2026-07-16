# Discord beta channel — ready-to-paste setup

Use this when standing up (or fixing) the CitiesAI beta feedback channel. I cannot edit your Discord server from here — copy the blocks below into Discord, then wire the webhook (step 4).

## 1. Channel layout

**Option A — dedicated CitiesAI server (small private beta)**

| Channel | Type | Purpose |
|---------|------|---------|
| `#welcome` | text | Pinned install guide + rules |
| `#citiesai-feedback` | text | In-app feedback webhook (read-only for members) |
| `#beta-chat` | text | Tester questions and discussion |
| `#announcements` | announcement | Version bumps, known issues |

**Option B — channel inside an existing CS2 server**

Create `#citiesai-feedback` (webhook only) and post the beta recruitment copy in your mod-tools or community channel.

## 2. `#citiesai-feedback` settings

1. **Edit channel** → **Overview**
   - **Channel name:** `citiesai-feedback`
   - **Topic:** `Automated feedback from CitiesAI beta builds. Use the in-app Feedback tab to report bugs.`
2. **Permissions** (recommended)
   - `@everyone`: **View Channel** ✓, **Send Messages** ✗, **Add Reactions** ✓
   - You (admin): full access
3. **Integrations** → **Webhooks** → **New Webhook**
   - **Name:** `CitiesAI Feedback`
   - **Channel:** `#citiesai-feedback`
   - **Save** → **Copy Webhook URL**

Treat the URL like a password. Never commit it.

## 3. Pin this in `#welcome` (or `#beta-chat`)

```text
CitiesAI Beta — quick start
──────────────────────────

CitiesAI is a free Windows companion for Cities: Skylines II. It reads a live snapshot of your city (population, budget, services, traffic) and answers questions grounded in your numbers + wiki knowledge. Read-only — never touches your save.

Requirements
• Windows 10/11 + CS2 (Steam or Game Pass)
• No Python, Unity, or modding experience
• Optional: free Mistral API key for AI answers (stats work without it)

Install
1. Download CitiesAI-Setup-0.9.1.exe from https://github.com/XharvaK/CitiesAI/releases
2. Run installer — SmartScreen may warn (unsigned beta); More info → Run anyway
3. Launch CitiesAI → complete onboarding (detect game → install mod → load a city)
4. Dashboard + Issues refresh ~every 10s while you play

Report bugs
Use the in-app Feedback tab (not this channel). Submissions land here automatically when configured.

Full guide: https://github.com/XharvaK/CitiesAI/blob/master/docs/BETA.md
```

## 4. Wire the webhook (maintainer)

```powershell
cd C:\Users\Xharv\Projects\CitiesAI
notepad packaging\secrets.local.env
```

Set:

```env
CITIESAI_DISCORD_WEBHOOK=https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN
```

Test without printing the URL:

```powershell
uv run python -c "from citiesai.feedback import submit_feedback; r=submit_feedback(category='setup-test', message='Webhook test — safe to delete.', contact='Doc'); print(r.get('mode'), r.get('warning', 'ok'))"
```

Expect `discord ok`. If you see `403 Forbidden`, the webhook was deleted — create a new one in step 2.

Rebuild so testers get the webhook in the installer:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build-release.ps1
```

## 5. Beta recruitment post (paste in CS2 Discord / Reddit)

See [beta-post.md](beta-post.md) for Discord short + Reddit long variants.

## 6. What testers see in `#citiesai-feedback`

Each in-app submission posts an embed:

- **Title:** `CitiesAI feedback: {category}`
- **Fields:** Version, Contact (optional), Issue context (if from Issues tab)
- **Optional:** System info (platform, export stale, LLM configured)

Categories: `bug`, `wrong answer`, `ux`, `feature`, `general`.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Webhook test returns `403 Forbidden` | Old webhook deleted. Create new webhook, update `secrets.local.env`, rebuild. |
| App says "Saved locally" | Installer built without webhook. Rebuild after step 4. |
| Spam in feedback channel | Delete webhook, create new one, update secrets. Consider a private server. |

More detail: [FEEDBACK-DISCORD.md](FEEDBACK-DISCORD.md)
