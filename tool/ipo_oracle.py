# tool/ipo_oracle.py
#
# Minimal oracle module used ONLY by the IPO runner.
# This file contains no batch-oracle functionality.
# It provides only:
#   - LTL negation
#   - nuXmv trace execution for a single LTL formula
#   - classification of a single CTD row (feasible / infeasible)
#

from __future__ import annotations
from pathlib import Path
from typing import Dict, Optional, Any, Tuple
import subprocess
import tempfile

from .ltl_builder import build_ltl_for_row
from .config_schema import ToolConfig


# ------------------------------------------------------------
# 1. Negate an LTL formula
# ------------------------------------------------------------

def negate_ltl(formula: str) -> str:
    """Return the negation !(...) unless already wrapped."""
    trimmed = formula.strip()
    if trimmed.startswith("!(") and trimmed.endswith(")"):
        return trimmed
    return f"!({trimmed})"


# ------------------------------------------------------------
# 2. Low-level nuXmv execution (single formula)
# ------------------------------------------------------------

def run_ltlspec_with_trace(
    model_path: str,
    ltl_formula: str,
    trace_output_path: str,
    nuxmv_bin: str = "nuXmv",
) -> Tuple[int, str, str]:
    """
    Run nuXmv with a single LTL formula and capture the trace.

    nuXmv writes a file "1_<trace_output>" in its working directory.
    We rename it to <trace_output> for consistency.
    """
    model = Path(model_path)
    if not model.exists():
        raise FileNotFoundError(f"SMV model not found: {model}")

    model_abs = model.resolve()
    trace_out = Path(trace_output_path)
    out_dir = trace_out.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    out_name = trace_out.name  # e.g. run_A0_B3_C1.txt

    # nuXmv writes the trace as 1_<out_name>
    nuxmv_generated = out_dir / f"1_{out_name}"

    # nuXmv command script
    script = f"""
read_model -i "{model_abs}"
flatten_hierarchy
encode_variables
build_model -f -m Threshold
check_ltlspec -p "{ltl_formula}"
show_traces -a -v -o "{out_name}"
quit
""".lstrip()

    # Write script to temp file
    with tempfile.NamedTemporaryFile("w", suffix=".cmd", delete=False) as tmp:
        tmp_path = Path(tmp.name)
        tmp.write(script)

    # Run nuXmv inside output dir
    try:
        completed = subprocess.run(
            [nuxmv_bin, "-source", str(tmp_path)],
            text=True,
            capture_output=True,
            cwd=str(out_dir),
        )
    finally:
        # Remove tmp script
        try:
            tmp_path.unlink()
        except OSError:
            pass

    # Rename 1_<name> → <name> if exists
    if nuxmv_generated.exists():
        try:
            if trace_out.exists():
                trace_out.unlink()
            nuxmv_generated.rename(trace_out)
        except OSError:
            pass

    return completed.returncode, completed.stdout, completed.stderr


# ------------------------------------------------------------
# 3. Classification for a single CTD row
# ------------------------------------------------------------

def classify_row_with_nuxmv(
    model_path: str,
    cfg: ToolConfig,
    row: Dict[str, Any],
    row_index: int,
    out_dir: str,
    nuxmv_bin: str = "nuXmv",
    trace_path_override: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Classify a single CTD row using LTL negation logic:

        - Build phi from (cfg, row)
        - Compute neg_phi
        - Check neg_phi via nuXmv
        - If neg_phi is FALSE --> phi is satisfiable --> feasible
        - If neg_phi is TRUE  --> phi is unsatisfiable --> infeasible

    Returns:
        {
          "row_index": int,
          "row": row,
          "phi": str,
          "neg_phi": str,
          "feasible": bool,
          "trace_path": str,
        }
    """

    out_dir_path = Path(out_dir)
    out_dir_path.mkdir(parents=True, exist_ok=True)

    # Use provided trace filename or fallback to run_rowNN.txt
    if trace_path_override is not None:
        trace_path = Path(trace_path_override)
    else:
        trace_path = out_dir_path / f"run_row{row_index:02d}.txt"

    # Build LTL formula
    phi = build_ltl_for_row(cfg, row)
    neg_phi = negate_ltl(phi)

    # Run nuXmv on neg_phi
    rc, stdout, stderr = run_ltlspec_with_trace(
        model_path=model_path,
        ltl_formula=neg_phi,
        trace_output_path=str(trace_path),
        nuxmv_bin=nuxmv_bin,
    )

    # Determine feasibility
    text = stdout + "\n" + stderr
    if " is false" in text:
        feasible = True
    elif " is true" in text:
        feasible = False
    else:
        # Fallback if nuXmv output changes
        feasible = False

    return {
        "row_index": row_index,
        "row": row,
        "phi": phi,
        "neg_phi": neg_phi,
        "feasible": feasible,
        "trace_path": str(trace_path),
    }
