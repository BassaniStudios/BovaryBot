# Deploy guide — Bova's Bot

## 1. Bot (Discord process)

Same method as before — nothing fundamental changed.

```bash
# On your host (VPS, Replit, Railway, etc.)
cd BovaryBot
pip install -r requirements.txt
cp .env.example .env
# Edit .env → set TOKEN, PANEL_URL, PANEL_ACCESS_ROLE_ID, channel IDs
python bot.py
```

### Discord Developer Portal
Invite the bot **without** Kick Members / Ban Members if you want to match the code
(those commands were removed). Still need:

- Manage Messages  
- Manage Roles (for auto-role)  
- Send Messages, Embed Links, Add Reactions, Read Message History  
- Privileged intents: **Message Content**, **Server Members**

After first run, slash commands sync automatically (`GUILD_ID` in `.env` makes sync faster).

### Data files (created at runtime)
- `data/cooldowns.json` — invite cooldowns  
- `data/autorole.json` — auto-role config  
- `data/meets.json` — scheduled meet reminders  
- `data/stats.json` — activity tracking  

Keep these if you restart the bot.

---

## 2. Web panel (static)

The panel is static HTML/CSS/JS in `web/`.

### Option A — GitHub Pages (recommended)
1. Create a repo (e.g. `BovaryBot-Panel`)
2. Upload the contents of the `web/` folder to the repo root  
   (index.html, css/, js/)
3. Settings → Pages → Deploy from branch `main` / root
4. URL will be like `https://USERNAME.github.io/BovaryBot-Panel/`
5. Put that URL in `.env` as `PANEL_URL`
6. Staff uses `/panel` on Discord → gets link + key `BOVA-CORE-2026`

### Option B — Same machine as the bot
Serve the folder with any static server, or extend Flask in `keep_alive.py`.

Change the access key in `web/js/app.js` (`ACCESS_KEY`) if you want.

---

## 3. Auto-role workflow
1. Configure title/description/roles on the web panel (export JSON) **or** use  
   `/autorole_add` + `/autorole_config` on Discord  
2. Post the panel: `/autorole_panel`  
3. Members click buttons to toggle roles  

## 4. Meet announcements
Use `/meet` with title, description, date (`DD/MM/YYYY HH:MM` São Paulo), hosts, server, optional image URL, optional reminder channel + enable flag.

## 5. Stats
Runs automatically in the background. Staff:
- `/stats` — overview  
- `/topmedia` — preview top media  
- `/topmedia post:True` — publish highlight  

---

**Summary:** Bot deploy is the same as before (`python bot.py` + `.env`).  
Web panel is a separate static deploy (GitHub Pages). Link them with `PANEL_URL`.
