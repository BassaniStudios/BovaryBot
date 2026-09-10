# Bova's Bot

Official bot of **Bovary Club Society**.

## Features
- Auto-reactions on media channels  
- Invite request panel (persistent cooldown)  
- Logs (members, channels, message delete/edit)  
- Moderation: `/delete`, `/purge` (no kick/ban)  
- Auto-role panel (buttons)  
- Car meet announcements + 30-min reminder  
- Server stats + top media of the period  
- Utilities: `/ping`, `/info`, `/timestamp`, `/help`  
- Cyberpunk Discord panel + external web dashboard  

## Quick start
```bash
pip install -r requirements.txt
cp .env.example .env   # set TOKEN
python bot.py
```

See **DEPLOY.md** for full deploy instructions (bot + web panel).

## Structure
```
BovaryBot/
├── bot.py
├── keep_alive.py
├── cogs/          # moderation, utilities, invite, events, autorole, meets, stats
├── utils/
├── data/          # runtime JSON
└── web/           # static control panel
```

## License
MIT — BassaniStudios / Bovary Club Society  
created by Bassani
