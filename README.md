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
3. Env minimum: `TOKEN`, `GUILD_ID`, `PANEL_ACCESS_KEY=BovaClub#CoreAccess-2026!`, `STAFF_API_ROLE_ID`, `CORS_ORIGIN`
4. Optional: `GROQ_API_KEY`, `LASTFM_API_KEY`, `DATABASE_PATH`
5. Panel: upload `web/`, set `BOVA_API.baseUrl`

**Important (Render free):** disk is ephemeral. After deploy run `/backup_export file:db` and save the file locally.

See **sumario.txt**.
