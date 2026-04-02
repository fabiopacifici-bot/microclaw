"""
skills.py — Load and execute SKILL.md files.
Reads frontmatter, exposes skill list, runs via model.infer().
"""
import os
import re
import yaml
from pathlib import Path


def _parse_skill(path: Path) -> dict | None:
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
        "instructions": m.group(2).strip(),
        "path": str(path),
    }


def load_all(skills_dir="./skills") -> list[dict]:
    skills = []
    for skill_md in Path(skills_dir).rglob("SKILL.md"):
        s = _parse_skill(skill_md)
        if s:
            skills.append(s)
    return skills


def find(name: str, skills: list[dict]) -> dict | None:
    name = name.lower().strip()
    return next((s for s in skills if s["name"].lower() == name), None)


def run(skill: dict, user_input: str, infer_fn) -> str:
    """Execute a skill by injecting its instructions as system context."""
    messages = [
        {"role": "system", "content": skill["instructions"]},
        {"role": "user", "content": user_input},
    ]
    return infer_fn(messages)
