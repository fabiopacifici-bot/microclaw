# MicroClaw

> A local-first, voice-native, skill-compatible AI agent powered by Gemma 4 E2B-it.  
> Smaller than NanoClaw. Zero cloud. Zero token cost. Runs on the edge.

---

## What is MicroClaw?

MicroClaw is a lightweight agent tier that sits below OpenClaw/NanoClaw in the hierarchy.  
It handles the cheap, frequent, low-stakes work locally — so the main session agent (Olly) only gets invoked when real reasoning is needed.

**Key properties:**
- 🎙️ **Voice-native** — audio in / audio out using Gemma 4 E2B's native audio support (no separate Whisper + TTS chain)
- 💰 **Zero token cost** — runs 100% locally, no API keys, no cloud
- 🔌 **Skills/Routines compatible** — reads `SKILL.md` and `ROUTINE.md` format natively
- 🤝 **OpenClaw-coordinated** — registers as a sub-agent, accepts delegated tasks from the main session
- 🔁 **Replicable** — spawns specialist sub-agents when task complexity demands, within memory limits
- 🌐 **Clusterable** — multiple nodes discover each other on LAN, any node can orchestrate

---

## Architecture

### Single Node

```
User voice/text
      ↓
MicroClaw Agent (Gemma 4 E2B-it)
      ↓ triage
  Can handle locally?
      ├── YES → execute (skill/routine/tool)
      └── NO  → delegate to OpenClaw main session (Olly)
      ↓
Voice/text response
```

### Multi-Agent (Shared Model)

```
Orchestrator MicroClaw
      ↓ spawns (if VRAM headroom allows)
[Researcher]  [Coder]  [Reviewer]  [Reporter]
      ↑
Shared Gemma E2B weights (loaded once)
Isolated context windows per agent
```

**Memory rule:**  
`max_replicas = floor(available_vram / CONTEXT_BUDGET_PER_REPLICA)`  
Replicas only spawn when headroom exists. Hard cap configurable. No memory explosion.

### Cluster (Multi-Node)

```
Node A (Pi)      Node B (Laptop)      Node C (Docker)
MicroClaw ────── MicroClaw ────────── MicroClaw
      ↑ LAN discovery via mDNS / static config
      ↑ any node can orchestrate
      ↑ task delegation via local HTTP API
```

---

## Stack

| Component | Technology |
|---|---|
| Model | Gemma 4 E2B-it (HuggingFace) |
| Inference | `transformers` + CUDA or CPU |
| Audio I/O | Gemma 4 native audio (mic → model → speaker) |
| API | FastAPI (same pattern as Fantasia/Olly Voice) |
| Skills | SKILL.md format (OpenClaw compatible) |
| Routines | ROUTINE.md format |
| Coordination | OpenClaw sub-agent protocol |
| Clustering | mDNS discovery + FastAPI mesh |
| Adapters | LoRA for specialist roles (optional) |

---

## Directory Structure

```
microclaw/
├── src/
│   ├── agent.py          # Core agent loop — triage, execute, delegate
│   ├── model.py          # Gemma 4 E2B loader + shared inference
│   ├── audio.py          # Native audio I/O via Gemma 4 audio support
│   ├── replica.py        # Replica spawner — memory-aware, role-assigned
│   ├── cluster.py        # Node discovery + task mesh
│   ├── skills.py         # SKILL.md loader + executor
│   ├── routines.py       # ROUTINE.md loader + executor
│   └── api.py            # FastAPI server — local + mesh endpoints
├── skills/               # Local skill definitions (SKILL.md)
├── routines/             # Local routine definitions (ROUTINE.md)
├── docs/
│   ├── ARCHITECTURE.md
│   └── CLUSTER_SETUP.md
├── tests/
├── README.md
├── requirements.txt
└── config.yaml           # Model path, VRAM limits, replica caps, cluster peers
```

---

## Replica Roles (LoRA adapters — optional)

| Role | Specialisation | When spawned |
|---|---|---|
| `orchestrator` | Task decomposition, delegation | Default / always |
| `researcher` | Web search, document reading | Research tasks |
| `coder` | Code generation, file editing | Dev tasks |
| `reviewer` | Output validation, diff review | After builder completes |
| `reporter` | Summary generation, Telegram delivery | After task completion |

Without LoRA: all roles use the base model, orchestrator assigns context via system prompt.  
With LoRA: each role loads a small adapter (~50-200MB) for specialisation.

---

## Self-Replication Rules

1. Orchestrator checks available VRAM before spawning any replica
2. Each replica gets a `CONTEXT_BUDGET` (default: 512MB VRAM for context)
3. `max_replicas = floor(free_vram / CONTEXT_BUDGET)` — hard ceiling
4. Replicas are ephemeral — destroyed when their task completes
5. No replica can spawn further replicas (depth limit = 1 by default, configurable)
6. All replicas share the loaded model weights (no duplicate loading)

---

## OpenClaw Integration

MicroClaw registers itself as a sub-agent on startup:

```python
# On init: register with OpenClaw main session
POST /api/subagent/register
{
  "id": "microclaw-local",
  "capabilities": ["exec", "skills", "routines", "voice"],
  "model": "gemma-4-E2B-it",
  "endpoint": "http://localhost:8769"
}
```

Olly can then delegate:
```
"Run the morning-briefing routine locally"
→ OpenClaw routes to MicroClaw
→ MicroClaw executes, reports back
→ Zero tokens consumed
```

---

## Course Integration (Multistack AI Developer — Week 7)

Building a working MicroClaw instance is the Week 7 deliverable:
- Students install Gemma 4 E2B locally
- Wire audio I/O  
- Load and execute one skill
- Optional: spawn one specialist replica

Demonstrates the human/agent layer concept running entirely offline.

---

## Status

🚧 **Concept stage** — Gemma 4 E2B-it downloading now.  
Next: basic agent loop + audio I/O prototype.

**Model:** `/mnt/e/models/huggingface/hub/models--google--gemma-4-E2B-it/`
