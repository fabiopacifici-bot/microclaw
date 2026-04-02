"""
routines.py — Load and execute ROUTINE.md files.
Reads steps, runs them in order via model.infer() or direct exec.
"""
import re
import yaml
import subprocess
from pathlib import Path


def _parse_routine(path: Path) -> dict | None:
    text = path.read_text()
    m = re.match(r"^---\n(.*?)\n---\n(.*)", text, re.DOTALL)
    if not m:
        return None
    try:
        fm = yaml.safe_load(m.group(1))
    except Exception:
        return None
    return {
        "name": fm.get("name", path.parent.name),
        "description": fm.get("description", ""),
        "trigger": fm.get("trigger", {}),
        "body": m.group(2).strip(),
        "path": str(path),
    }


def load_all(routines_dir="./routines") -> list[dict]:
    routines = []
    for r_md in Path(routines_dir).rglob("ROUTINE.md"):
        r = _parse_routine(r_md)
        if r:
            routines.append(r)
    return routines


def find(name: str, routines: list[dict]) -> dict | None:
    name = name.lower().strip()
    return next((r for r in routines if r["name"].lower() == name), None)


def run(routine: dict, infer_fn) -> str:
    """Execute a routine: pass its body as system prompt, ask model to execute steps."""
    messages = [
        {"role": "system", "content": f"You are executing the following routine. Follow each step precisely and report results.\n\n{routine['body']}"},
        {"role": "user", "content": f"Execute the {routine['name']} routine now."},
    ]
    return infer_fn(messages, max_new_tokens=1024)
