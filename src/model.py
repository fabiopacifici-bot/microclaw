"""
model.py — Load Gemma 4 E2B-it and expose inference + audio.
One model loaded once. All agents share it.
"""
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
    model_path = cfg["model"]["path"]
    device = cfg["model"].get("device", "cuda" if torch.cuda.is_available() else "cpu")
    dtype = getattr(torch, cfg["model"].get("dtype", "bfloat16"))

    print(f"[model] Loading {model_path} on {device} ({dtype})")
    _processor = AutoProcessor.from_pretrained(model_path)
    _model = AutoModelForCausalLM.from_pretrained(
        model_path, torch_dtype=dtype, device_map="auto"
    )
    print(f"[model] Ready")
    return _model, _processor


def infer(messages: list, max_new_tokens=512) -> str:
    """Run a chat completion. messages = OpenAI-style list."""
    model, processor = _model, _processor
    inputs = processor.apply_chat_template(
        messages, add_generation_prompt=True, tokenize=True, return_tensors="pt"
    ).to(model.device)
    with torch.no_grad():
        out = model.generate(inputs, max_new_tokens=max_new_tokens, do_sample=False)
    return processor.decode(out[0][inputs.shape[-1]:], skip_special_tokens=True)


def vram_free_mb() -> int:
    """Return free VRAM in MB, or RAM if CPU."""
    if torch.cuda.is_available():
        free, _ = torch.cuda.mem_get_info()
        return free // (1024 * 1024)
    import psutil
    return psutil.virtual_memory().available // (1024 * 1024)
