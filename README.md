# Bova's Bot — v2.4-sql

Private bot for **Bovary Club Society**. Developed by **Bassani**.

## Storage
- **SQLite** primary (`data/bovary.db`, WAL mode)
- Auto-migrates legacy `data/*.json` on first boot
- API remains `load_json` / `save_json` (cogs unchanged)
- Audit in native `audit_log` table
- Export: `/backup_export file:db` or `file:all`

## Quick deploy
1. Push to bot GitHub repo
2. Render: `pip install -r requirements.txt` → `python bot.py`
3. Env minimum: `TOKEN`, `GUILD_ID`, `PANEL_ACCESS_KEY=CHANGE_ME_IN_RENDER`, `STAFF_API_ROLE_ID`, `CORS_ORIGIN`
4. Optional: `GROQ_API_KEY`, `LASTFM_API_KEY`, `DATABASE_PATH`
5. Panel: upload `web/`, set `BOVA_API.baseUrl`

**Important (Render free):** disk is ephemeral. After deploy run `/backup_export file:db` and save the file locally.

See **sumario.txt**.


## Member Join/Leave Logs — v2.8.0

The member log is driven directly by Discord's native Guild Members Gateway events. No slash command is required at runtime.

**Required:** enable **Server Members Intent** in the Discord Developer Portal and keep `intents.members = True` in `bot.py`. The configured Info Log channel is `LOG_CHANNEL_ID=1441663299065217114`; the resolver also recovers `#id-info` from the main guild if the stored channel ID became stale.

Join/leave embeds include the member identity, ID, account creation time, join time, server member count, membership duration, roles available at the event, avatar and a UTC timestamp.
