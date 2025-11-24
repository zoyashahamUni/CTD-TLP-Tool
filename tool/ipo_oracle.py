from __future__ import annotations
from pathlib import Path
from typing import Dict, Optional, Any, Tuple
import subprocess
import tempfile

from .ltl_builder import build_ltl_for_row, _expr_for_factor_value
from .config_schema import ToolConfig

def _render_value_for_ltl(v: object) -> str:
    """Render Python values into SMV LTL constants."""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    return str(v)

def build_ltl_for_partial_assignment(cfg: ToolConfig, assignment: Dict[str, object]) -> str:
    """
    Build an LTL formula for a *partial* factor assignment, using the
    same "Option B" mapping as build_ltl_for_row, and including the
    end-of-test flag.

    Example:
        assignment = {"a_no_logout_after_add": False, "b_max_items": 3}

    Produces something like:
        F(end_of_test & no_logout_after_add = FALSE & max_items = 3)
    """
    parts = []

    # 1) end_of_test flag (same as build_ltl_for_row)
    parts.append(cfg.end_flag)

    # 2) Only include factors that appear in this partial assignment
    for f in cfg.factors:
        name = f.name
        if name not in assignment:
            continue
        v = assignment[name]
        expr = _expr_for_factor_value(name, v)
        parts.append(expr)

    inside = " & ".join(parts)
    return cfg.ltl_template.format(conditions=inside)

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

def classify_partial_with_nuxmv(
    model_path: str,
    cfg: ToolConfig,
    assignment: Dict[str, object],
    label: str,
    out_dir: str,
    nuxmv_bin: str = "nuXmv",
) -> Dict[str, Any]:
    """
    Classify a *partial* assignment (e.g. a single pair) as globally
    feasible/infeasible.

    - assignment: subset of {factor_name: value}, e.g. {"A": 0, "C": 1}
    - label: used only for naming the trace file, e.g. "PAIR_A0_C1"

    Semantics:
      phi := F(end_of_test & conjunction(assignment))
      We check !phi with nuXmv:
        - if !phi is FALSE → phi is satisfiable → feasible = True
        - if !phi is TRUE  → phi is UNSAT       → feasible = False
    """
    out_dir_path = Path(out_dir)
    out_dir_path.mkdir(parents=True, exist_ok=True)

    # Use a deterministic but simple trace name based on label
    trace_path = out_dir_path / f"run_{label}.txt"

    # 1) Build phi for the partial assignment
    phi = build_ltl_for_partial_assignment(cfg, assignment)
    # 2) Negate it
    neg_phi = negate_ltl(phi)

    # 3) Run nuXmv on !phi
    rc, stdout, stderr = run_ltlspec_with_trace(
        model_path=model_path,
        ltl_formula=neg_phi,
        trace_output_path=str(trace_path),
        nuxmv_bin=nuxmv_bin,
    )

    # 4) Interpret nuXmv output in the same way as for full rows
    text = stdout + "\n" + stderr
    if " is false" in text:
        feasible = True
    elif " is true" in text:
        feasible = False
    else:
        feasible = False  # conservative default

    return {
        "assignment": assignment,
        "label": label,
        "phi": phi,
        "neg_phi": neg_phi,
        "feasible": feasible,
        "trace_path": str(trace_path),
    }

