# Bot profile & privacy

## Banner / avatar
The bot does **NOT** overwrite profile assets unless `APPLY_BOT_PROFILE=true`.

Set banner and icon in: **Discord Developer Portal → Your App → Bot**.

### Animated avatar (GIF)
A ready-to-use square GIF focused on the robot is included at:

`assets/bovas_bot_avatar.gif`

To apply it automatically on boot:

```
APPLY_BOT_PROFILE=true
BOT_AVATAR_FILE=assets/bovas_bot_avatar.gif
```

You can also use a hosted URL with `BOT_AVATAR_URL=` instead.

If the banner/avatar still reverts, check Render env is `APPLY_BOT_PROFILE=false` (or unset).

## Bio (Developer Portal → Application description)
```
Bova's Bot — private operations core for Bovary Club Society.

Moderation · media reactions · meets · tickets · stats · structured logs.

Private crew bot. Developed by Bassani.
```

## Make the bot private (hide "Add to Server")
Discord controls this — not the Python code:

1. Discord Developer Portal → Application
2. **Installation** / **Bot** settings
3. Turn **Public Bot** **OFF** (or disable default authorization link / install link)
4. Do not share OAuth2 invite URLs

The bot will only exist on servers where you already added it with your owner account.
