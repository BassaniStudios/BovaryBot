# Deploy guide — Bova's Bot

## 1. Bot (Discord process)

```bash
cd BovaryBot
pip install -r requirements.txt
cp .env.example .env
# Edit .env → TOKEN, GUILD_ID, channel IDs, PANEL_URL, PANEL_ACCESS_KEY
python bot.py
```

### Discord Developer Portal
Invite with:
- Manage Messages, Manage Roles, Manage Channels (tickets)
- Send Messages, Embed Links, Add Reactions, Read Message History, Attach Files
- Privileged intents: **Message Content**, **Server Members**

Slash commands sync automatically (`GUILD_ID` makes sync faster).

### Data files (created at runtime)
- `data/cooldowns.json`
- `data/autorole.json`
- `data/meets.json`
- `data/stats.json`
- `data/autofeeds.json`
- `data/boost.json`
- `data/tickets.json`
- `data/weblogs.json`
- `data/transcripts/` — ticket transcripts

Keep these across restarts. Storage uses atomic writes + `.bak` backups.

### Health check
If using `keep_alive.py`: `GET /health` returns JSON `{ status, uptime_seconds }`.

---

## 2. Web panel (static)

### GitHub Pages (recommended)
1. Repo e.g. `BovaryBot-Panel`
2. Upload contents of `web/` to repo root
3. Settings → Pages → branch `main` / root
4. Set `PANEL_URL` in bot `.env`
5. Staff: `/panel` → link; enter the key privately on the web panel

**Panel access:** set `PANEL_ACCESS_KEY` only as a private Render environment variable; the key is never stored in the static frontend or displayed by `/panel`.

**Roles / channels** for dropdowns: edit `web/js/config.js`.

---

## 3. Log channel map
| Event | Default channel ID | Env var |
|-------|--------------------|---------|
| Join / leave | 1441663299065217114 (Info) | `LOG_CHANNEL_ID` |
| Admin (purge, tickets, channels) | 1424436722984423529 (bot-room) | `BOT_ROOM_CHANNEL_ID` |
| Message delete/edit | 1432715549116207248 | `MESSAGE_LOG_CHANNEL_ID` |
| Boost thank-you | 1384173136638906407 | `BOOST_CHANNEL_ID` |

---

## 4. Common workflows
**Auto-role:** `/autorole_add` (repeat for each role) → `/autorole_panel`  
**Meet:** `/meet` with date_time `DD/MM/YYYY HH:MM` (São Paulo)  
**Tickets:** `/ticket_setup` → `/ticket_panel`  
**Auto-feed:** `/autofeed_add` (interval or `fixed_hour` + optional `use_embed:True`)  
**Logs toggles:** `/weblogs_config`

---

**Summary:** Bot = `python bot.py` + `.env`. Panel = static GitHub Pages. Link with `PANEL_URL`.

---

## Turso (remote SQLite) — recommended on Render free

1. Create a database at https://turso.tech (free tier is enough).
2. Copy the URL and create a token:
   ```bash
   turso db show --url <db-name>
   turso db tokens create <db-name>
   ```
3. On Render → Environment:
   ```
   TURSO_DATABASE_URL=libsql://....turso.io
   TURSO_AUTH_TOKEN=...
   ```
4. Redeploy. The bot will use Turso instead of the local `data/bovary.db`.
5. Discord auto-backup remains as an optional extra export; file restore is skipped in remote mode.

To migrate existing local data once: run the bot once with local DB (no Turso vars), then set Turso vars and use a one-shot export/import, or keep the JSON migration path on first Turso connect if `data/*.json` still exist.

