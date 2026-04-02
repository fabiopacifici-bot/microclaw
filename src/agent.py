"""
agent.py — Core MicroClaw agent loop.
Triage: handle locally or escalate to OpenClaw.
"""
import requests
import yaml
from model import infer, vram_free_mb
from skills import load_all as load_skills, find as find_skill, run as run_skill
from routines import load_all as load_routines, find as find_routine, run as run_routine
from replica import spawn, active as active_replicas, can_spawn

_config = None
_skills = []
_routines = []


def init(config_path="config.yaml"):
    global _config, _skills, _routines
    with open(config_path) as f:
        _config = yaml.safe_load(f)
    _skills   = load_skills(_config.get("skills_dir", "./skills"))
    _routines = load_routines(_config.get("routines_dir", "./routines"))
    print(f"[agent] {len(_skills)} skills, {len(_routines)} routines loaded")


def triage(text: str) -> str:
    """
    Classify and handle a user request.
    Returns the response string.
    """
    lower = text.lower()

    # --- Routine trigger ---
    for r in _routines:
        if r["name"].lower() in lower or f"run {r['name'].lower()}" in lower:
            print(f"[agent] Running routine: {r['name']}")
            return run_routine(r, infer)

    # --- Skill trigger ---
    for s in _skills:
        if s["name"].lower() in lower:
            print(f"[agent] Running skill: {s['name']}")
            return run_skill(s, text, infer)

    # --- Status / system queries ---
    if any(w in lower for w in ["status", "vram", "replicas", "health"]):
        replicas = active_replicas()
        return (
            f"MicroClaw status:\n"
            f"  VRAM free: {vram_free_mb()} MB\n"
            f"  Active replicas: {len(replicas)}/{3}\n"
            f"  Can spawn: {can_spawn()}\n"
            f"  Skills: {len(_skills)}\n"
            f"  Routines: {len(_routines)}"
        )

    # --- Direct inference (local) ---
    messages = [
        {"role": "system", "content": "You are MicroClaw, a concise local AI assistant. Answer helpfully and briefly."},
        {"role": "user",   "content": text},
    ]
    return infer(messages)


def escalate(text: str) -> str:
    """Delegate to OpenClaw main session."""
    endpoint = _config.get("api", {}).get("openclaw_endpoint", "http://localhost:18789")
    try:
        r = requests.post(f"{endpoint}/api/message", json={"message": text}, timeout=10)
        return r.json().get("reply", "Escalated to Olly.")
    except Exception as e:
        return f"Escalation failed: {e}"
