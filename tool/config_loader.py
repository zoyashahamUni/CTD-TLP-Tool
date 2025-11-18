# tool/config_loader.py
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Union, List, Dict, Any
from .config_schema import validate_and_build_config, ToolConfig


# ============================
#   REGEX DEFINITIONS
# ============================

# Start block:  -- ctd_factors:
_FACTORS_START = re.compile(r"^\s*--\s*ctd_factors\s*:\s*$", re.IGNORECASE)

# End block OPTIONAL. If missing, we stop reading when a blank line appears
_FACTORS_END = re.compile(r"^\s*--\s*end_ctd_factors\s*$", re.IGNORECASE)

# Interface:  -- ctd_interfacing: step=step; mode=mode; end=end_of_test
_INTERFACING = re.compile(r"^\s*--\s*ctd_interfacing\s*:\s*(.+)$", re.IGNORECASE)

# Template:   -- ctd_ltl_template: F({conditions})
_LTL_TEMPLATE = re.compile(r"^\s*--\s*ctd_ltl_template\s*:\s*(.+)$", re.IGNORECASE)

# Factor line:   --   name:kind{vals}
_LINE_RX = re.compile(
    r"^\s*--\s*(?P<name>[a-z_][a-z0-9_]*)\s*:\s*"
    r"(?P<kind>boolean|integer)"
    r"(?:\{(?P<vals>[^\}]*)\})?\s*$",
    re.IGNORECASE,
)


# ============================
#   JSON LOADER
# ============================

def load_json_config(path: Union[str, Path]) -> ToolConfig:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {p}")
    raw = json.loads(p.read_text(encoding="utf-8"))
    return validate_and_build_config(raw)


# ============================
#   INLINE SMV PARSER
# ============================

def _parse_inline_config_from_smv_text(text: str) -> ToolConfig:
    lines = text.splitlines()

    in_block = False
    raw_factors: List[Dict[str, Any]] = []

    step_var = "step"
    mode_var = "mode"
    end_flag = "end_of_test"
    ltl_template = "F({conditions})"   # default

    for line in lines:

        # --- START OF FACTORS BLOCK ---
        if _FACTORS_START.match(line):
            in_block = True
            continue

        # --- END OF FACTORS BLOCK ---
        if in_block and _FACTORS_END.match(line):
            in_block = False
            continue

        # --- FACTOR LINE ---
        if in_block:
            m = _LINE_RX.match(line)
            if m:
                name = m.group("name").lower()
                kind = m.group("kind").lower()
                vals = m.group("vals")

                if kind == "boolean":
                    raw_factors.append({"name": name, "type": "boolean"})

                elif kind == "integer":
                    if not vals:
                        raise ValueError(f"Integer factor '{name}' missing values")
                    nums = [int(v.strip()) for v in vals.split(",") if v.strip()]
                    raw_factors.append({"name": name, "type": "integer", "values": nums})

            # Optional: stop block on blank line
            if line.strip() == "":
                in_block = False

        # --- INTERFACING LINE ---
        m2 = _INTERFACING.match(line)
        if m2:
            for part in m2.group(1).split(";"):
                part = part.strip()
                if "=" in part:
                    k, v = [x.strip() for x in part.split("=", 1)]
                    k = k.lower()
                    if k == "step":
                        step_var = v
                    elif k == "mode":
                        mode_var = v
                    elif k in ("end", "end_flag"):
                        end_flag = v

        # --- LTL TEMPLATE LINE ---
        m3 = _LTL_TEMPLATE.match(line)
        if m3:
            ltl_template = m3.group(1).strip()

    # --- NO FACTORS FOUND ---
    if not raw_factors:
        raise ValueError("No inline ctd_factors block found in SMV")

    # --- BUILD RAW CONFIG ---
    raw = {
        "factors": raw_factors,
        "ltl_template": ltl_template,
        "step_var": step_var,
        "mode_var": mode_var,
        "end_flag": end_flag,
    }

    return validate_and_build_config(raw)


def load_inline_config_from_smv(path: Union[str, Path]) -> ToolConfig:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"SMV file not found: {p}")

    text = p.read_text(encoding="utf-8")
    return _parse_inline_config_from_smv_text(text)
