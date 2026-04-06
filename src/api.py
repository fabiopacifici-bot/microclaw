"""
api.py — FastAPI server. Local + mesh endpoints.
Port 8769 by default.
"""
from fastapi import FastAPI
from pydantic import BaseModel
import yaml, agent, replica as rep, model as mdl
import bootstrap as _bootstrap
import os

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = FastAPI(title="MicroClaw", version="0.1.0")

_cfg = {}


class MessageIn(BaseModel):
    message: str

class TaskIn(BaseModel):
    role: str
    task: str


@app.on_event("startup")
async def startup():
    global _cfg
    with open(os.path.join(_BASE, "config.yaml")) as f:
        _cfg = yaml.safe_load(f)
    # Bootstrap skills and routines from ecosystem repos
    counts = _bootstrap.bootstrap(_cfg)
    if counts["skills"] or counts["routines"]:
        print(f"[bootstrap] Added {counts['skills']} skills, {counts['routines']} routines from ecosystem")

    _config_path = os.path.join(_BASE, "config.yaml")
    mdl.load(_config_path)
    agent.init(_config_path)
    print(f"[api] MicroClaw ready on :{_cfg['api']['port']}")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "vram_free_mb": mdl.vram_free_mb(),
        "active_replicas": len(rep.active()),
        "skills": len(agent._skills),
        "routines": len(agent._routines),
    }


@app.post("/message")
def message(body: MessageIn):
    """Main entry point — triage and respond."""
    reply = agent.triage(body.message)
    return {"reply": reply}


@app.get("/skills")
def list_skills():
    return [{"name": s["name"], "description": s["description"]} for s in agent._skills]


@app.get("/routines")
def list_routines():
    return [{"name": r["name"], "description": r["description"], "trigger": r["trigger"]} for r in agent._routines]


@app.post("/replica/spawn")
def spawn_replica(body: TaskIn):
    """Spawn a specialist replica if VRAM allows."""
    r = rep.spawn(body.role, body.task)
    if r is None:
        return {"status": "rejected", "reason": "VRAM limit or replica cap reached"}
    return {"status": "spawned", "role": r.role}


@app.get("/replica/active")
def active_replicas():
    return [{"role": r.role, "task": r.task[:80], "done": r.done} for r in rep.active()]


@app.get("/system")
def system_info():
    return {
        "vram_free_mb": mdl.vram_free_mb(),
        "can_spawn": rep.can_spawn(),
        "max_replicas": rep.MAX_REPLICAS,
        "context_budget_mb": rep.CONTEXT_BUDGET_MB,
    }
