# Bova's Bot — v2.14.0

Private bot for **Bovary Club Society**. Developed by **Bassani**.

## What's new in 2.14.0
- **Bovary Economy** (`cogs/economy.py`) — sistema completo de economia
  - Moeda: **Bovas coins**
  - Painel fixo de membros no canal **Bovary Bank** (botões, sem slash para membros)
  - Respostas dos membros vão para **Bovary Market**
  - Painel admin [LOCKED] no canal **Bank Admin**
  - Daily com streak, work, pay, shop (pets / carros / brasões), inventário, ranking
  - Mini-games interativos: **Mines**, **Hack**, **Coinflip**
  - Staff: add/remove/set money, all-users, reset, settings, shop CRUD, backup wallets
  - Slash: `/economy panel`, `/economy adminpanel`, `/economy balance`

## What's new in 2.13.0
- **Anti-spam honeypot** (`cogs/antispam.py`)
  - Channel `ANTISPAM_CHANNEL_ID` (default `1559213282638827590`)
  - Any message → immediate **native Discord timeout (7 days)**
  - Immune: bots, owner (`921803925051572266`), crew-leader role, Administrators
  - Public embed in honeypot + detailed staff log in WebLogs
  - Slash (LOCKED): `/antispam`, `/antispam_toggle`, `/antispam_status`

---
# Legacy header note (v2.12.0 Turso-ready patch)

Private bot for **Bovary Club Society**. Developed by **Bassani**.

## Storage
- **SQLite** primary (`data/bovary.db`, WAL mode) **or Turso remote**
- Auto-migrates legacy `data/*.json` on first boot
- API remains `load_json` / `save_json` (cogs unchanged)
- Audit in native `audit_log` table
- Export: `/backup_export file:db` or `file:all`

## Turso (recomendado para Render Free)
Para não perder dados após re-deploy:

1. Crie o banco em https://app.turso.tech
2. Clique em **+ Create Token** e copie o token
3. No Render → Environment Variables:
   ```
   TURSO_DATABASE_URL=libsql://bovarybot-bassanistudios.aws-us-east-1.turso.io
   TURSO_AUTH_TOKEN=seu_token_aqui
   ```
4. No `requirements.txt` adicione:
   ```
   libsql
   ```
5. Faça redeploy

Com Turso ativo o bot grava tudo na nuvem. `/topmedia` e outros comandos deixam de perder memória.

## Quick deploy
1. Push to bot GitHub repo
2. Render: `pip install -r requirements.txt` → `python bot.py`
3. Env minimum: `TOKEN`, `GUILD_ID`, `PANEL_ACCESS_KEY=CHANGE_ME_IN_RENDER`, `STAFF_API_ROLE_ID`, `CORS_ORIGIN`
4. Optional: `GROQ_API_KEY`, `LASTFM_API_KEY`, `DATABASE_PATH`, `TURSO_*`
5. Panel: upload `web/`, set `BOVA_API.baseUrl`

**Important (Render free):** disk is ephemeral. Prefer Turso. After deploy you can still run `/backup_export file:db` as safety copy.

See **sumario.txt**.

## Fixes in this patch
- Removed duplicate `_export_snapshot_bytes` function in `cogs/backup.py` (was causing potential empty backups)
- Full Turso support confirmed and documented
