# tool/oracle.py
from __future__ import annotations
from pathlib import Path
from typing import Tuple, Dict, Optional
from .ltl_builder import build_ltl_for_row
from .config_schema import ToolConfig
import subprocess
import tempfile

def negate_ltl(formula: str) -> str:
    # just add !(...) around the string we get.
    trimmed = formula.strip()
    # If it's already of the form !(...), don't double-wrap
    if trimmed.startswith("!(") and trimmed.endswith(")"):
        return trimmed
    return f"!({trimmed})"

def run_ltlspec_with_trace(
    model_path: str,
    ltl_formula: str,
    trace_output_path: str,
    nuxmv_bin: str = "nuXmv",
) -> Tuple[int, str, str]:
    """
    Run nuXmv on a model with a single LTL formula and write the trace to a file.

    This function:
      1) builds a small nuXmv command script:
         - read_model -i "<model_path>"
         - flatten_hierarchy
         - encode_variables
         - build_model -f -m Threshold
         - check_ltlspec -p "<ltl_formula>"
         - show_traces -a -v -o "<basename>"
         - quit
      2) calls: nuXmv -source <script> with cwd = output directory
      3) renames "1_<basename>" → "<basename>" if such a file exists.

    It does NOT parse the trace; it only makes sure nuXmv runs and writes it.
    """
    model = Path(model_path)
    if not model.exists():
        raise FileNotFoundError(f"SMV model not found: {model}")
    # absolute path so it works even when cwd = output/
    model_abs = model.resolve()

    trace_out = Path(trace_output_path)
    out_dir = trace_out.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    out_name = trace_out.name  # e.g. "run_row01.txt"

    # nuXmv will actually create "1_<basename>" in cwd
    nuxmv_output_name = f"1_{out_name}"
    nuxmv_output_path = out_dir / nuxmv_output_name

    # Build the nuXmv command script
    script = f'''
read_model -i "{model_abs}"
flatten_hierarchy
encode_variables
build_model -f -m Threshold
check_ltlspec -p "{ltl_formula}"
show_traces -a -v -o "{out_name}"
quit
'''.lstrip()

    # Write script to a temporary file
    with tempfile.NamedTemporaryFile("w", suffix=".cmd", delete=False) as tmp:
        tmp_path = Path(tmp.name)
        tmp.write(script)

    # Run nuXmv with the script, in the output directory
    try:
        completed = subprocess.run(
            [nuxmv_bin, "-source", str(tmp_path)],
            text=True,
            capture_output=True,
            cwd=str(out_dir),          # run inside output dir
        )
    finally:
        # Best-effort cleanup of the temp script
        try:
            tmp_path.unlink()
        except OSError:
            pass

    # If nuXmv produced "1_<basename>", rename it to the requested path
    if nuxmv_output_path.exists():
        try:
            if trace_out.exists():
                trace_out.unlink()
            nuxmv_output_path.rename(trace_out)
        except OSError:
            # If rename fails, we still return stdout/stderr
            pass

    return completed.returncode, completed.stdout, completed.stderr

def run_negated_ltlspec_with_trace(
    model_path: str,
    ltl_formula: str,
    trace_output_path: str,
    nuxmv_bin: str = "nuXmv",
):
    """
    CTD–TLP wrapper:
    Given an ltl formula, automatically negates it
    then runs nuXmv on the negated formula.

    If the negated formula produces a counterexample - the row is feasible.
    If the negated formula has no counterexample     - the row is infeasible.
    """
    neg = negate_ltl(ltl_formula)
    return run_ltlspec_with_trace(
        model_path=model_path,
        ltl_formula=neg,
        trace_output_path=trace_output_path,
        nuxmv_bin=nuxmv_bin,
    )

def classify_row_with_nuxmv(
    model_path: str,
    cfg: ToolConfig,
    row: Dict[str, object],
    row_index: int,
    out_dir: str,
    nuxmv_bin: str = "nuXmv",
    trace_path_override: Optional[str] = None,
):
    """
    Classify a single CTD row as feasible/infeasible using nuXmv.

    Returns a dict with:
      - row_index
      - row
      - phi
      - neg_phi
      - feasible
      - trace_path
    """
    out_dir_path = Path(out_dir)
    out_dir_path.mkdir(parents=True, exist_ok=True)
    
    # If caller provided a custom filename (e.g. run_A0_B3_C0.txt), use it
    if trace_path_override is not None:
        trace_path = Path(trace_path_override)
    else:
        # fallback: old behavior
        trace_path = out_dir_path / f"run_row{row_index:02d}.txt"


    # 1) Build phi (non-negated)
    phi = build_ltl_for_row(cfg, row)

    # 2) Negate - not phi
    neg_phi = negate_ltl(phi)

    # 3) Run nuXmv on not phi
    rc, stdout, stderr = run_ltlspec_with_trace(
        model_path=model_path,
        ltl_formula=neg_phi,
        trace_output_path=str(trace_path),
        nuxmv_bin=nuxmv_bin,
    )

    # 4) Determine feasibility:
    #    If "is false" → negation is false - phi is satisfiable - feasible
    #    If "is true"  → negation is true  - phi is unsatisfiable - infeasible
    text = stdout + "\n" + stderr
    if " is false" in text:
        feasible = True
    elif " is true" in text:
        feasible = False
    else:
        feasible = False  # default fallback

    return {
        "row_index": row_index,
        "row": row,
        "phi": phi,
        "neg_phi": neg_phi,
        "feasible": feasible,
        "trace_path": str(trace_path),
    }