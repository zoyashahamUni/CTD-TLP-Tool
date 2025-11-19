# tool/config_loader.py
from __future__ import annotations
import json
from pathlib import Path
from typing import Union, List, Dict, Any
from .config_schema import validate_and_build_config, ToolConfig


# ============================
#   JSON LOADER
# ============================

def load_json_config(path: Union[str, Path]) -> ToolConfig:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {p}")
    raw = json.loads(p.read_text(encoding="utf-8"))
    return validate_and_build_config(raw)

