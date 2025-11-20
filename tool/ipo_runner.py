# tool/ipo_runner.py
from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, List, Set
from itertools import product

from .config_schema import ToolConfig
from .generator import _domains_from_factors, _pairs_for_row
from .ipo_oracle import classify_row_with_nuxmv    # << UPDATED IMPORT


Row = Dict[str, Any]


def _all_pairs(names: List[str], doms: Dict[str, List[Any]]) -> Set[frozenset]:
    """Return the full required 2-way pair universe."""
    universe = set()
    for combo in product(*[doms[n] for n in names]):
        row = dict(zip(names, combo))
        universe |= _pairs_for_row(row)
    return universe


def run_ipo_with_oracle(model_path: str, cfg: ToolConfig, out_dir: str):
    """
    Full 2-phase IPO runner:
      Phase 1: Stream A-B, choose best C each time, run nuXmv immediately.
      Phase 2: Coverage completion: add only rows that fill missing pairs.
    """
    doms = _domains_from_factors(cfg.factors)
    names = [f.name for f in cfg.factors]

    if len(names) != 3:
        raise ValueError("IPO runner currently supports exactly 3 factors (A,B,C).")

    A, B, C = names
    out_dir_path = Path(out_dir)
    out_dir_path.mkdir(parents=True, exist_ok=True)

    all_required_pairs = _all_pairs(names, doms)
    covered_pairs: Set[frozenset] = set()

    feasible_profiles = []
    infeasible_profiles = []
    global_index = 0
    seen_profiles = set()

    # -------------------------------
    # PHASE 1 — STREAM A–B, choose C
    # -------------------------------

    rows_phase1: List[Row] = []

    for a_val in doms[A]:
        for b_val in doms[B]:

            # pick C maximizing new pair coverage
            best_c = None
            best_gain = -1

            for c_val in doms[C]:
                candidate = {A: a_val, B: b_val, C: c_val}
                pairs = _pairs_for_row(candidate)
                gain = sum(1 for p in pairs if p not in covered_pairs)
                if gain > best_gain:
                    best_gain = gain
                    best_c = c_val

            row = {A: a_val, B: b_val, C: best_c}
            rows_phase1.append(row)

            # classify immediately
            profile = _profile_name_from_row(row)
            seen_profiles.add(profile)
            trace_file = out_dir_path / f"run_{profile}.txt"

            global_index += 1
            result = classify_row_with_nuxmv(
                model_path=model_path,
                cfg=cfg,
                row=row,
                row_index=global_index,
                out_dir=out_dir,
                trace_path_override=str(trace_file),
            )

            if result["feasible"]:
                feasible_profiles.append(profile)
            else:
                infeasible_profiles.append(profile)

            # update coverage
            covered_pairs |= _pairs_for_row(row)

    # ----------------------------------
    # PHASE 2 — COVERAGE COMPLETION
    # ----------------------------------
    uncovered = all_required_pairs - covered_pairs

    rows_phase2: List[Row] = []

    while uncovered:
        best_row = None
        best_gain = 0

        for combo in product(*[doms[n] for n in names]):
            candidate = dict(zip(names, combo))
            profile = _profile_name_from_row(candidate)
            if profile in seen_profiles:
                continue  # already tested in Phase 1

            pairs = _pairs_for_row(candidate)
            gain = sum(1 for p in pairs if p in uncovered)
            if gain > best_gain:
                best_gain = gain
                best_row = candidate

        if best_row is None or best_gain == 0:
            break

        rows_phase2.append(best_row)

        profile = _profile_name_from_row(best_row)
        seen_profiles.add(profile)
        trace_file = out_dir_path / f"run_{profile}.txt"

        global_index += 1
        result = classify_row_with_nuxmv(
            model_path=model_path,
            cfg=cfg,
            row=best_row,
            row_index=global_index,
            out_dir=out_dir,
            trace_path_override=str(trace_file),
        )

        if result["feasible"]:
            feasible_profiles.append(profile)
        else:
            infeasible_profiles.append(profile)

        covered_pairs |= _pairs_for_row(best_row)
        uncovered = all_required_pairs - covered_pairs

    # ---- Write summary files ----
    (out_dir_path / "feasible.txt").write_text(
        "\n".join(feasible_profiles) + "\n", encoding="utf-8"
    )
    (out_dir_path / "infeasible.txt").write_text(
        "\n".join(infeasible_profiles) + "\n", encoding="utf-8"
    )

    return {
        "feasible": feasible_profiles,
        "infeasible": infeasible_profiles,
        "rows_phase1": rows_phase1,
        "rows_phase2": rows_phase2,
    }


def _profile_name_from_row(row: Dict[str, Any]) -> str:
    """
    Build a short profile name from a row, e.g.
    {'a_no_logout_after_add': False, 'b_max_items': 3, 'c_no_remove': True}
    -> 'A0_B3_C1'
    """
    parts = []
    for name in sorted(row.keys()):
        v = row[name]
        if isinstance(v, bool):
            num = 1 if v else 0
        else:
            num = v
        abbrev = name[0].upper()
        parts.append(f"{abbrev}{num}")
    return "_".join(parts)
