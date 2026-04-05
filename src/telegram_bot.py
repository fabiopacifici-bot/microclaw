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


def send_buttons(chat_id: str, text: str, buttons: list):
    """Send a message with inline keyboard buttons."""
    try:
        requests.post(f"{API_BASE}/sendMessage", json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "reply_markup": {"inline_keyboard": buttons},
        }, timeout=10)
    except Exception as e:
        print(f"[bot] send_buttons error: {e}")


def handle_callback(chat_id: str, data: str, message_id: int):
    """Handle inline button callbacks."""
    if data.startswith("routine_run_"):
        name = data[12:]
        handle_message(chat_id, f"/run {name}")
    elif data.startswith("routine_info_"):
        name = data[13:]
        _ensure_agent()
        import yaml
        with open(CONFIG_PATH) as _f: _cfg = yaml.safe_load(_f)
        from routines import load_all, find
        routines = load_all(_cfg.get("routines_dir", str(Path(__file__).parent.parent / "routines")))
        r = find(name, routines)
        if r:
            trigger = r.get("trigger", {})
            t = trigger.get("also", trigger.get("cron", "manual")) if isinstance(trigger, dict) else "manual"
            send_message(chat_id, f"*{r['name']}*\n_{r['description']}_\nTrigger: `{t}`\n\nTap ▶ Run to execute.")
    elif data.startswith("skill_info_"):
        name = data[11:]
        _ensure_agent()
        import yaml
        with open(CONFIG_PATH) as _f: _cfg = yaml.safe_load(_f)
        from skills import load_all, find
        skills = load_all(_cfg.get("skills_dir", str(Path(__file__).parent.parent / "skills")))
        s = find(name, skills)
        if s:
            send_message(chat_id, f"*{s['name']}*\n_{s['description']}_")


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
        import yaml
        with open(CONFIG_PATH) as _f: _cfg = yaml.safe_load(_f)
        from skills import load_all
        skills = load_all(_cfg.get("skills_dir", str(Path(__file__).parent.parent / "skills")))
        if not skills:
            send_message(chat_id, "🔧 No skills loaded.")
        else:
            # Send as inline buttons (2 per row)
            buttons = []
            row = []
            for s in skills:
                row.append({"text": s['name'], "callback_data": f"skill_info_{s['name']}"})
                if len(row) == 2:
                    buttons.append(row)
                    row = []
            if row:
                buttons.append(row)
            send_buttons(chat_id, f"🔧 *Skills ({len(skills)}) — tap to learn more:*", buttons)
        return

    if text == "/routines":
        _ensure_agent()
        import yaml
        with open(CONFIG_PATH) as _f: _cfg = yaml.safe_load(_f)
        from routines import load_all
        routines = load_all(_cfg.get("routines_dir", str(Path(__file__).parent.parent / "routines")))
        if not routines:
            send_message(chat_id, "⚙️ No routines loaded.")
        else:
            # Send as inline buttons — one per row with Run button
            buttons = []
            for r in routines:
                buttons.append([
                    {"text": f"⚙️ {r['name']}", "callback_data": f"routine_info_{r['name']}"},
                    {"text": "▶ Run", "callback_data": f"routine_run_{r['name']}"}
                ])
            send_buttons(chat_id, f"⚙️ *Routines ({len(routines)}):*", buttons)
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
    from model import infer
    from pathlib import Path

    # Load persona from AGENTS.md
    agents_file = Path(__file__).parent.parent / "AGENTS.md"
    system_prompt = agents_file.read_text() if agents_file.exists() else "You are MicroClaw, a concise local AI assistant."

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": text}
    ]
    reply = infer(messages, max_new_tokens=512)
    send_message(chat_id, f"🦞 {reply}")


CONFIG_PATH = str(Path(__file__).parent.parent / "config.yaml")


def _ensure_agent():
    global _agent_ready
    if not _agent_ready:
        # Load model first (bot runs in its own process — globals don't carry over from API server)
        import model as _model_module
        if _model_module._model is None:
            _model_module.load(CONFIG_PATH)
        # Then init agent
        import agent
        agent.init(CONFIG_PATH)
        _agent_ready = True


def poll():
    """Long-poll Telegram for updates."""
    offset = None
    print(f"[bot] MicroClaw Telegram bot starting...")

    while True:
        try:
            params = {"timeout": 30, "allowed_updates": ["message", "callback_query"]}
            if offset:
                params["offset"] = offset

            resp = requests.get(f"{API_BASE}/getUpdates", params=params, timeout=35)
            data = resp.json()

            for update in data.get("result", []):
                offset = update["update_id"] + 1
                # Handle callback queries (button taps)
                cb = update.get("callback_query", {})
                if cb:
                    cb_chat = cb.get("message", {}).get("chat", {}).get("id")
                    cb_data = cb.get("data", "")
                    cb_msg_id = cb.get("message", {}).get("message_id")
                    if cb_chat and cb_data:
                        threading.Thread(
                            target=handle_callback,
                            args=(str(cb_chat), cb_data, cb_msg_id),
                            daemon=True
                        ).start()
                    # Answer callback to remove loading state
                    try:
                        requests.post(f"{API_BASE}/answerCallbackQuery",
                            json={"callback_query_id": cb.get("id", "")}, timeout=5)
                    except: pass
                    continue

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
    print("[bot] Pre-loading model...")
    import model as _model_module
    _model_module.load(CONFIG_PATH)
    print("[bot] Model ready, starting polling...")
    poll()
