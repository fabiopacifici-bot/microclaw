"""
model.py — Load Gemma 4 E2B-it and expose inference + audio.
One model loaded once. All agents share it.
"""
import os
import torch
import yaml
from pathlib import Path
from transformers import AutoProcessor, AutoModelForCausalLM

_model = None
_processor = None
_config = None


def load_config(path="config.yaml"):
    global _config
    with open(path) as f:
        _config = yaml.safe_load(f)
    return _config


def load(config_path="config.yaml"):
    global _model, _processor, _config
    if _model:
        return _model, _processor

    cfg = load_config(config_path)
    model_source = os.environ.get("MODEL_SOURCE", "local")

    if model_source == "docker-hub":
        # Docker Model Runner: use model ID directly, HuggingFace will resolve it
        # Full Docker Model Runner API integration pending (docker/model-runner)
        model_path = os.environ.get("MODEL_ID", cfg["model"]["name"])
        print(f"[model] Docker Hub mode — using {model_path}")
    else:
        model_path = cfg["model"]["path"]

    device = cfg["model"].get("device", "cuda" if torch.cuda.is_available() else "cpu")
    dtype = getattr(torch, cfg["model"].get("dtype", "bfloat16"))

    print(f"[model] Loading {model_path} on {device} ({dtype})")
    _processor = AutoProcessor.from_pretrained(model_path)
    _model = AutoModelForCausalLM.from_pretrained(
        model_path, dtype=dtype, device_map="auto"
    )
    print(f"[model] Ready")
    return _model, _processor


def infer(messages: list, max_new_tokens=512) -> str:
    """Run a chat completion. messages = OpenAI-style list with string content."""
    # Gemma 4 processor requires content as list of dicts with 'type' key
    formatted = []
    for m in messages:
        content = m["content"]
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        formatted.append({"role": m["role"], "content": content})

    inputs = _processor.apply_chat_template(
        formatted,
        add_generation_prompt=True,
        tokenize=True,
        return_tensors="pt"
    ).to(_model.device)

    with torch.no_grad():
        out = _model.generate(inputs, max_new_tokens=max_new_tokens, do_sample=False)
    return _processor.decode(out[0][inputs.shape[-1]:], skip_special_tokens=True)


def infer_with_tools(
    messages: list,
    tools: list,
    workspace: str = "/home/pacificDev/.openclaw/workspace",
    max_steps: int = 15,
) -> str:
    """
    Agentic inference loop with native function calling.
    Gemma emits tool calls → we execute them → feed results back → repeat until final answer.
    Returns the final text response.
    """
    from tools import execute_tool
    import json

    current_messages = [m.copy() for m in messages]

    for step in range(max_steps):
        formatted = []
        for m in current_messages:
            content = m["content"]
            if isinstance(content, str):
                content = [{"type": "text", "text": content}]
            entry = {"role": m["role"], "content": content}
            if "name" in m:
                entry["name"] = m["name"]
            formatted.append(entry)

        text = _processor.apply_chat_template(
            formatted,
            tools=tools,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )
        inputs = _processor(text=text, return_tensors="pt").to(_model.device)
        input_len = inputs["input_ids"].shape[-1]

        with torch.no_grad():
            out = _model.generate(
                **inputs,
                max_new_tokens=512,
                do_sample=False,
                temperature=1.0,
                top_p=0.95,
                top_k=64,
            )

        response_text = _processor.decode(out[0][input_len:], skip_special_tokens=True)

        tool_call = _parse_tool_call(response_text)
        if tool_call is None:
            return response_text.strip()

        tool_name = tool_call.get("name") or tool_call.get("function", {}).get("name", "")
        tool_args = tool_call.get("arguments") or tool_call.get("function", {}).get("arguments", {})
        if isinstance(tool_args, str):
            try:
                tool_args = json.loads(tool_args)
            except Exception:
                tool_args = {}

        print(f"[tool] {tool_name}({json.dumps(tool_args)[:80]}...)", flush=True)
        result = execute_tool(tool_name, tool_args, workspace=workspace)
        print(f"[tool] result: {result[:100]}...", flush=True)

        current_messages.append({"role": "assistant", "content": response_text})
        current_messages.append({
            "role": "tool",
            "content": json.dumps({"result": result}),
            "name": tool_name,
        })

    return "(max steps reached)"


def _parse_tool_call(text: str) -> "dict | None":
    """Try to extract a tool call JSON from model output."""
    import json
    import re

    # Pattern 1: Gemma 4 native format — call:tool_name{arg:val, ...}
    m = re.search(r"call:(\w+)\{([^}]*)\}", text)
    if m:
        tool_name = m.group(1)
        raw_args = m.group(2)
        # Parse key:value pairs (simple, not full JSON)
        args = {}
        for pair in re.findall(r'(\w+):\s*([^,}]+)', raw_args):
            args[pair[0].strip()] = pair[1].strip().strip('"').strip("'")
        return {"name": tool_name, "arguments": args}

    # Pattern 2: JSON code block
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass

    # Pattern 3: <tool_call> tags
    m = re.search(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass

    # Pattern 4: OpenAI-style {"name": ..., "arguments": {...}}
    m = re.search(r'(\{"name":\s*"[^"]+",\s*"arguments":\s*\{.*?\}\s*\})', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass

    # Pattern 5: Raw JSON object with name/function key
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            data = json.loads(stripped)
            if "name" in data or "function" in data:
                return data
        except Exception:
            pass

    return None


def vram_free_mb() -> int:
    """Return free VRAM in MB, or RAM if CPU."""
    if torch.cuda.is_available():
        free, _ = torch.cuda.mem_get_info()
        return free // (1024 * 1024)
    import psutil
    return psutil.virtual_memory().available // (1024 * 1024)
