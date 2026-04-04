"""
telegram_bot.py — MicroClaw's own Telegram bot.
Runs independently — no Olly in the loop.
Connects directly: Telegram → Gemma 4 local → Telegram

Usage: python src/telegram_bot.py
"""
import os
import json
import requests
import threading
import time
import sys
from pathlib import Path

# Add src/ to path
sys.path.insert(0, str(Path(__file__).parent))

BOT_TOKEN = os.environ.get("MICROCLAW_TELEGRAM_BOT_TOKEN")
ALLOWED_CHAT_ID = os.environ.get("MICROCLAW_TELEGRAM_CHAT_ID")
API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Lazy model load
_agent_ready = False

def send_message(chat_id: str, text: str, parse_mode: str = "Markdown"):
    try:
        requests.post(f"{API_BASE}/sendMessage", json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }, timeout=10)
    except Exception as e:
        print(f"[bot] send error: {e}")


def handle_message(chat_id: str, text: str):
    global _agent_ready

    # Auth check
    if ALLOWED_CHAT_ID and str(chat_id) != str(ALLOWED_CHAT_ID):
        send_message(chat_id, "❌ Unauthorized.")
        return

    text = text.strip()

    # Slash commands
    if text in ("/start", "/help"):
        send_message(chat_id, (
            "🦞 *MicroClaw*\n"
            "Local AI agent — Gemma 4 E2B-it — zero cloud\n\n"
            "Commands:\n"
            "/skills — list available skills\n"
            "/routines — list available routines\n"
            "/status — system status\n"
            "/run `<routine>` — execute a routine\n\n"
            "Or just type anything to chat."
        ))
        return

    if text == "/skills":
        _ensure_agent()
        from skills import load_all
        skills = load_all(str(Path(__file__).parent.parent / "skills"))
        if not skills:
            send_message(chat_id, "🔧 No skills loaded.")
        else:
            lines = [f"🔧 *Skills ({len(skills)}):*"]
            for s in skills:
                lines.append(f"• `{s['name']}` — {s['description'][:60]}")
            send_message(chat_id, "\n".join(lines))
        return

    if text == "/routines":
        _ensure_agent()
        from routines import load_all
        routines = load_all(str(Path(__file__).parent.parent / "routines"))
        if not routines:
            send_message(chat_id, "⚙️ No routines loaded.")
        else:
            lines = [f"⚙️ *Routines ({len(routines)}):*"]
            for r in routines:
                trigger = r.get("trigger", {})
                t = trigger.get("also", trigger.get("cron", "manual")) if isinstance(trigger, dict) else "manual"
                lines.append(f"• `{r['name']}` — {r['description'][:55]} _{t}_")
            send_message(chat_id, "\n".join(lines))
        return

    if text == "/status":
        import torch
        free_mb = 0
        if torch.cuda.is_available():
            free, total = torch.cuda.mem_get_info()
            free_mb = free // (1024 * 1024)
        send_message(chat_id, (
            f"🦞 *MicroClaw Status*\n"
            f"Model: Gemma 4 E2B-it\n"
            f"VRAM free: {free_mb}MB\n"
            f"Ready: {'✅' if _agent_ready else '⏳ loading on first message'}"
        ))
        return

    if text.startswith("/run "):
        routine_name = text[5:].strip()
        send_message(chat_id, f"⚙️ Running routine `{routine_name}`...")
        _ensure_agent()
        from routines import load_all, find, run
        from model import infer
        routines = load_all(str(Path(__file__).parent.parent / "routines"))
        r = find(routine_name, routines)
        if not r:
            send_message(chat_id, f"❌ Routine `{routine_name}` not found.")
            return
        result = run(r, infer)
        send_message(chat_id, f"✅ `{routine_name}` complete:\n\n{result[:3000]}")
        return

    # Regular chat — route to agent
    if not _agent_ready:
        send_message(chat_id, "⏳ Loading model (~60s)...")

    _ensure_agent()
    from agent import triage
    reply = triage(text)
    send_message(chat_id, f"🦞 {reply}")


def _ensure_agent():
    global _agent_ready
    if not _agent_ready:
        import yaml
        config_path = str(Path(__file__).parent.parent / "config.yaml")
        import agent
        agent.init(config_path)
        _agent_ready = True


def poll():
    """Long-poll Telegram for updates."""
    offset = None
    print(f"[bot] MicroClaw Telegram bot starting...")

    while True:
        try:
            params = {"timeout": 30, "allowed_updates": ["message"]}
            if offset:
                params["offset"] = offset

            resp = requests.get(f"{API_BASE}/getUpdates", params=params, timeout=35)
            data = resp.json()

            for update in data.get("result", []):
                offset = update["update_id"] + 1
                msg = update.get("message", {})
                chat_id = msg.get("chat", {}).get("id")
                text = msg.get("text", "")
                if chat_id and text:
                    # Handle in thread so polling doesn't block
                    threading.Thread(
                        target=handle_message,
                        args=(str(chat_id), text),
                        daemon=True
                    ).start()

        except KeyboardInterrupt:
            print("[bot] Stopped.")
            break
        except Exception as e:
            print(f"[bot] Poll error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    if not BOT_TOKEN:
        print("ERROR: MICROCLAW_TELEGRAM_BOT_TOKEN not set in .env")
        sys.exit(1)

    # Load .env if not already loaded
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

    print(f"[bot] Starting MicroClaw bot (@clawmicrobot)")
    print(f"[bot] Allowed chat: {ALLOWED_CHAT_ID or 'all'}")
    poll()
