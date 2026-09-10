# Bova's Bot — v2.2-api

Private bot for **Bovary Club Society**. Developed by **Bassani**.

Includes HTTP API for the web panel (embed, meet, autorole, autofeed).

## Quick deploy
1. Push this folder to the **bot** GitHub repo (not the panel).
2. Render: `pip install -r requirements.txt` → `python bot.py`
3. Env: `TOKEN`, `GUILD_ID`, `PANEL_ACCESS_KEY`, `STAFF_API_ROLE_ID=1547647694997037137`, `CORS_ORIGIN`, `APPLY_BOT_PROFILE=false`
4. Panel repo: upload `web/` and set `BOVA_API.baseUrl` in `js/config.js` to the Render URL.

See **sumario.txt** and **BOT_PROFILE.md**.
