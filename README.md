# PteroGuardian

Automated server cleanup and protection for Pterodactyl panels.

## Features

- Detect inactive servers using panel database logs
- Automatic suspension and deletion based on thresholds
- Discord notifications for each action
- Role pings for weekly cleanup runs
- Protection keywords to prevent critical servers from being touched
- Weekly summary embed with totals and keywords
- Fully configurable via `config.json`

## Requirements

- Python 3.10+
- Libraries: requests, schedule, mysql-connector-python

Install requirements:

```bash
pip install -r requirements.txt
```

## Configuration

Create a `config.json`:

```json
{
    "discord": {
        "webhook_url": "https://discord.com/api/webhooks/XXXX/XXXX",
        "role_id": "123456789012345678"
    },
    "protection": {
        "keywords": ["[KEEP]", "[VIP]", "[NO-DELETE]"]
    },
    "database": {
        "host": "127.0.0.1",
        "user": "cleanup",
        "password": "password",
        "database": "panel"
    }
}
```

## Usage

```bash
python main.py
```

The script will:

1. Ping your Discord role at the start
2. Check all servers
3. Skip protected servers
4. Mark inactive servers
5. Suspend servers past inactivity threshold
6. Delete servers suspended too long
7. Send a summary embed

## Safety Tips

- Keep `DRY_RUN = True` until tested
- Use a read-only database user
- Keep `config.json` secure
