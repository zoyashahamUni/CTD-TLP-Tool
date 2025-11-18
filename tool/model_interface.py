# tool/model_interface.py
from __future__ import annotations
import re
from pathlib import Path
from typing import Tuple
from .config_schema import ToolConfig

# Match the VAR block only (from 'VAR' until the next major section keyword)
RE_VAR_BLOCK = re.compile(
    r"VAR(.*?)(?:ASSIGN|DEFINE|TRANS|INIT|INVAR|LTLSPEC)",
    re.S
)

def _extract_var_block(text: str) -> str:
    """Return the content of the VAR block, or '' if not found."""
    m = RE_VAR_BLOCK.search(text)
    return m.group(1) if m else ""

def _has_identifier(text: str, ident: str) -> bool:
    """Check if the given text contains a standalone identifier (not part of another word)."""
    rx = re.compile(rf"\b{re.escape(ident)}\b")
    return rx.search(text) is not None

def validate_model_contract(model_path: str, cfg: ToolConfig) -> Tuple[bool, str]:
    """
    Verify that the SMV model contains the required identifiers
    declared in the configuration: step_var, mode_var, end_flag.
    Returns (ok, message).
    """
    p = Path(model_path)
    if not p.exists():
        return False, f"SMV file not found: {model_path}"

    full_text = p.read_text(encoding="utf-8")

    # 🔥 New: restrict search to VAR block only
    var_block = _extract_var_block(full_text)

    if not var_block.strip():
        return False, "Could not find VAR block in SMV model."

    missing = []
    for label, ident in (
        ("step_var", cfg.step_var),
        ("mode_var", cfg.mode_var),
        ("end_flag", cfg.end_flag),
    ):
        if not _has_identifier(var_block, ident):
            missing.append(f"{label}='{ident}'")

    if missing:
        return False, "Missing required identifiers in VAR block: " + ", ".join(missing)

    return True, "Model contract OK"
