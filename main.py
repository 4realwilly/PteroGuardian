import requests
import json
import os
import time
import schedule
import mysql.connector
from datetime import datetime, timedelta, timezone

# ================= CORE CONFIG =================
PANEL_URL = 'https://panel.example.com'
ADMIN_API_KEY = 'ptla_your_api_key_here'

DAYS_INACTIVE_LIMIT = 2
DAYS_SUSPENDED_LIMIT = 2

STATE_FILE = 'server_state.json'
DRY_RUN = True
# ===============================================

# ================= LOAD CONFIG ==================
CONFIG_FILE = "config.json"

if not os.path.exists(CONFIG_FILE):
    raise RuntimeError("config.json missing")

with open(CONFIG_FILE, "r") as f:
    CONFIG = json.load(f)

DISCORD_WEBHOOK_URL = CONFIG["discord"]["webhook_url"]
DISCORD_ROLE_ID = CONFIG["discord"].get("role_id", "")
PROTECTED_KEYWORDS = [k.lower() for k in CONFIG["protection"]["keywords"]]

DB_CONFIG = CONFIG["database"]
# ===============================================

HEADERS = {
    'Authorization': f'Bearer {ADMIN_API_KEY}',
    'Accept': 'application/json',
    'Content-Type': 'application/json'
}

UTC = timezone.utc


# ---------------- DISCORD ----------------
def send_embed(title, description, color=15158332, ping=False):
    if not DISCORD_WEBHOOK_URL:
        return

    content = f"<@&{DISCORD_ROLE_ID}>" if ping and DISCORD_ROLE_ID else ""

    payload = {
        "content": content,
        "embeds": [{
            "title": title,
            "description": description,
            "color": color,
            "timestamp": datetime.now(UTC).isoformat()
        }]
    }

    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
    except Exception as e:
        print(f"[!] Discord error: {e}")


# ---------------- STATE ----------------
def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=4)


# ---------------- API ----------------
def get_all_servers():
    servers = []
    page = 1

    while True:
        r = requests.get(
            f"{PANEL_URL}/api/application/servers?page={page}",
            headers=HEADERS,
            timeout=30
        )
        if r.status_code != 200:
            raise RuntimeError(r.text)

        data = r.json()
        servers.extend(data.get('data', []))

        meta = data.get('meta', {}).get('pagination', {})
        if meta.get('current_page', 1) >= meta.get('total_pages', 1):
            break
        page += 1

    return servers


def suspend_server(server_id):
    if DRY_RUN:
        return True

    r = requests.post(
        f"{PANEL_URL}/api/application/servers/{server_id}/suspend",
        headers=HEADERS
    )
    return r.status_code == 204


def delete_server(server_id):
    if DRY_RUN:
        return True

    r = requests.delete(
        f"{PANEL_URL}/api/application/servers/{server_id}",
        headers=HEADERS
    )
    return r.status_code == 204


# ---------------- INACTIVITY ----------------
def get_last_activity(server_id):
    db = mysql.connector.connect(**DB_CONFIG)
    cursor = db.cursor()

    cursor.execute("""
        SELECT created_at
        FROM activity_logs
        WHERE subject_type = 'server'
          AND subject_id = %s
        ORDER BY created_at DESC
        LIMIT 1
    """, (server_id,))

    row = cursor.fetchone()
    cursor.close()
    db.close()

    if not row:
        return None

    return row[0].replace(tzinfo=UTC)


def is_inactive(server_id):
    last = get_last_activity(server_id)
    if not last:
        return True
    return datetime.now(UTC) - last > timedelta(days=DAYS_INACTIVE_LIMIT)


# ---------------- MAIN JOB ----------------
def manage_servers_job():
    counters = {
        "total": 0,
        "protected": 0,
        "inactive": 0,
        "suspended": 0,
        "deleted": 0
    }

    send_embed(
        "Weekly Server Cleanup Started",
        "Protected keywords:\n```" + "\n".join(PROTECTED_KEYWORDS) + "```",
        color=3447003,
        ping=True
    )

    state = load_state()
    servers = get_all_servers()
    counters["total"] = len(servers)

    for s in servers:
        a = s['attributes']
        sid = str(a['id'])
        name = a['name']
        suspended = a['is_suspended']
        now = datetime.now(UTC)

        matched = [k for k in PROTECTED_KEYWORDS if k in name.lower()]
        if matched:
            counters["protected"] += 1
            continue

        state.setdefault(sid, {})

        if suspended:
            if 'suspended_at' in state[sid]:
                suspended_at = datetime.fromisoformat(state[sid]['suspended_at'])
                if now - suspended_at > timedelta(days=DAYS_SUSPENDED_LIMIT):
                    if delete_server(sid):
                        counters["deleted"] += 1
                        state.pop(sid, None)
            else:
                state[sid]['suspended_at'] = now.isoformat()
            continue

        if is_inactive(sid):
            if 'inactive_since' not in state[sid]:
                state[sid]['inactive_since'] = now.isoformat()
                counters["inactive"] += 1
            else:
                inactive_since = datetime.fromisoformat(state[sid]['inactive_since'])
                if now - inactive_since > timedelta(days=DAYS_INACTIVE_LIMIT):
                    if suspend_server(sid):
                        counters["suspended"] += 1
                        state[sid]['suspended_at'] = now.isoformat()
        else:
            state.pop(sid, None)

    save_state(state)

    send_embed(
        "📊 Weekly Cleanup Summary",
        f"""
**Servers scanned:** {counters['total']}
🛡️ **Protected:** {counters['protected']}
⚠️ **Marked inactive:** {counters['inactive']}
⛔ **Suspended:** {counters['suspended']}
🗑️ **Deleted:** {counters['deleted']}

**Keywords in use:**
```{", ".join(PROTECTED_KEYWORDS)}```
""",
        color=10181046
    )


# ---------------- RUN ----------------
if __name__ == "__main__":
    schedule.every().week.do(manage_servers_job)

    print("Scheduler running (Ctrl+C to stop)")
    while True:
        schedule.run_pending()
        time.sleep(60)
