"""
bootstrap.py — Pull skills and routines from ecosystem repos on startup.
"""
import os
import subprocess
import yaml
from pathlib import Path


def bootstrap(config: dict) -> dict:
    """
    Pull skills and routines from ecosystem repos.
    Returns dict with counts: {skills: N, routines: N}
    """
    eco = config.get("ecosystem", {})
    if not eco.get("bootstrap_on_startup", False):
        return {"skills": 0, "routines": 0}

    cache_dir = Path(os.path.expanduser(eco.get("cache_dir", "~/.microclaw/ecosystem")))
    cache_dir.mkdir(parents=True, exist_ok=True)

    counts = {"skills": 0, "routines": 0}

    for repo_key in ["community", "private"]:
        repo = eco.get(repo_key)
        if not repo:
            continue
        branch = eco.get("branch", "main")
        local_path = cache_dir / repo_key

        try:
            if local_path.exists():
                # Pull latest
                result = subprocess.run(
                    ["git", "pull", "--ff-only"],
                    cwd=local_path, capture_output=True, text=True, timeout=30
                )
                print(f"[bootstrap] {repo_key}: {result.stdout.strip() or 'up to date'}")
            else:
                # Clone
                repo_url = f"https://github.com/{repo}.git"
                result = subprocess.run(
                    ["git", "clone", "--depth=1", "-b", branch, repo_url, str(local_path)],
                    capture_output=True, text=True, timeout=60
                )
                if result.returncode != 0:
                    print(f"[bootstrap] {repo_key}: clone failed — {result.stderr.strip()}")
                    continue
                print(f"[bootstrap] {repo_key}: cloned from {repo_url}")

            # Symlink or copy skills/ and routines/ into config paths
            skills_src = local_path / "skills"
            routines_src = local_path / "routines"
            skills_dst = Path(os.path.expanduser(
                os.environ.get("SKILLS_DIR") or config.get("skills_dir", "./skills")
            ))
            routines_dst = Path(os.path.expanduser(
                os.environ.get("ROUTINES_DIR") or config.get("routines_dir", "./routines")
            ))

            if skills_src.exists():
                skills_dst.mkdir(parents=True, exist_ok=True)
                for skill in skills_src.iterdir():
                    if skill.is_dir() and (skill / "SKILL.md").exists():
                        dest = skills_dst / skill.name
                        if not dest.exists():
                            dest.symlink_to(skill.resolve())
                            counts["skills"] += 1

            if routines_src.exists():
                routines_dst.mkdir(parents=True, exist_ok=True)
                for routine in routines_src.iterdir():
                    if routine.is_dir() and (routine / "ROUTINE.md").exists():
                        dest = routines_dst / routine.name
                        if not dest.exists():
                            dest.symlink_to(routine.resolve())
                            counts["routines"] += 1

        except Exception as e:
            print(f"[bootstrap] {repo_key}: error — {e}")

    return counts
