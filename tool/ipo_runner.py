# tool/ipo_runner.py
from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, List, Set, Optional
from .config_schema import ToolConfig
from .generator import _domains_from_factors, _pairs_for_row, generate_pairwise_twix
from .ipo_oracle import classify_row_with_nuxmv, classify_partial_with_nuxmv
from itertools import product

Row = Dict[str, Any]


def _all_pairs(names: List[str], doms: Dict[str, List[Any]]) -> Set[frozenset]:
    """Return the full required 2-way pair universe."""
    universe = set()
    for combo in product(*[doms[n] for n in names]):
        row = dict(zip(names, combo))
        universe |= _pairs_for_row(row)
    return universe

def _find_one_infeasible_pair_in_row(
    model_path: str,
    cfg: ToolConfig,
    row: Row,
    pairs_in_row: Set[frozenset],
    out_dir: str,
    infeasible_pairs: Set[frozenset],
    feasible_pairs: Set[frozenset],
    covered_pairs: Set[frozenset],
) -> frozenset:

    """
    Given an infeasible row, use the pair-level oracle to identify
    It returns the first infeasible pair it finds, or raises if none exist.

    Side effects:
      - Updates infeasible_pairs and feasible_pairs in-place.
      - Does NOT update covered_pairs (only full feasible rows do that).

    Strategy:
      - For each pair p in this row:
          * If already known infeasible -> return it immediately.
          * Else query nuXmv on that pair only.
              - If feasible -> mark p as feasible_pairs.
              - If infeasible -> add to infeasible_pairs and return.
      - If none found infeasible, raise an error (indicates >2-way constraint).
    """
    for p in sorted(pairs_in_row, key=lambda x: sorted(list(x))):
        # If we already know this pair is infeasible, we are done.
        if p in infeasible_pairs:
            return p

        # If we already know this pair is already covered by a feasible full row, skip it.
        if p in covered_pairs:
            continue

        # If we already know this pair is feasible (from a previous pair-level check),
        # no need to query nuXmv again.
        if p in feasible_pairs:
            continue

        # Decode frozenset({(name1, val1), (name2, val2)}) into dict
        assignment = dict(p)  # type: ignore[arg-type]

        # Build a readable label for trace naming, e.g. "PAIR_A0_C1"
        label_parts = []
        for name, val in assignment.items():
            label_parts.append(f"{name}{val}")
        label = "PAIR_" + "_".join(label_parts)

        result = classify_partial_with_nuxmv(
            model_path=model_path,
            cfg=cfg,
            assignment=assignment,
            label=label,
            out_dir=out_dir,
        )

        if result["feasible"]:
            # This pair is globally feasible (some completion exists),
            # but not yet covered by a full row.
            feasible_pairs.add(p)
        else:
            # We found a truly infeasible pair
            infeasible_pairs.add(p)
            return p


    # If we reach here, the row is infeasible but no pair was proven infeasible.
    # This suggests the model has higher-order (3-way+) constraints.
    raise RuntimeError(
        "Infeasible row but no infeasible pair found: "
        "model likely contains higher-order constraints "
        "beyond pairwise."
    )

def _build_row_around_pair(
    target_pair: frozenset,
    names: List[str],
    doms: Dict[str, List[object]],
    infeasible_pairs: Set[frozenset],
) -> Optional[Row]:
    """
    Given a target pair (as frozenset({(name1,val1), (name2,val2)})),
    build a full row that:
      - includes this pair, and
      - does not include any pair from infeasible_pairs (if possible).

    Returns:
      - dict factor_name -> value if a suitable row was found
      - None if no row can be built without using an infeasible pair
        (this would mean the pair is effectively infeasible).
    """
    # Start row with the target pair's assignments
    row: Row = dict(target_pair)  # type: ignore[arg-type]

    # Fill remaining factors one by one
    for name in names:
        if name in row:
            continue

        chosen_value = None
        for val in doms[name]:
            ok = True
            for existing_name, existing_val in row.items():
                p = frozenset({(name, val), (existing_name, existing_val)})
                if p in infeasible_pairs:
                    ok = False
                    break
            if ok:
                chosen_value = val
                break

        if chosen_value is None:
            # No value for this factor avoids known infeasible pairs
            return None

        row[name] = chosen_value

    return row

def run_ipo_with_oracle(model_path: str, cfg: ToolConfig, out_dir: str):
    """
    Full 2-phase IPO runner (generic over any number of factors):

  Phase 1: Use Twix pairwise generator to produce an initial covering set
           of rows. For each row, run nuXmv immediately and classify it.

  Phase 2: While there are uncovered pairs, pick one uncovered pair, 
  try to build a row around it avoiding known infeasible pairs, 
  classify it, and update coverage.
    """
    doms = _domains_from_factors(cfg.factors)
    names = [f.name for f in cfg.factors]

    out_dir_path = Path(out_dir)
    out_dir_path.mkdir(parents=True, exist_ok=True)

    all_required_pairs = _all_pairs(names, doms)
    covered_pairs: Set[frozenset] = set()
    infeasible_pairs: Set[frozenset] = set()
    feasible_pairs: Set[frozenset] = set()
    
    feasible_profiles: List[str] = []
    infeasible_profiles: List[str] = []
    global_index = 0
    seen_profiles: Set[str] = set()
    
    # -------------------------------
    # PHASE 1 
    # -------------------------------

    rows_phase1: List[Row] = []

    twix_rows = generate_pairwise_twix(cfg.factors)

    for row in twix_rows:
        rows_phase1.append(row)

        profile = _profile_name_from_row(row)
        if profile in seen_profiles:
            continue
        seen_profiles.add(profile)

        trace_file = out_dir_path / f"run_{profile}.txt"

        global_index += 1

        # NEW: compute pairs_in_row once
        pairs_in_row = _pairs_for_row(row)

        result = classify_row_with_nuxmv(
            model_path=model_path,
            cfg=cfg,
            row=row,
            row_index=global_index,
            out_dir=out_dir,
            trace_path_override=str(trace_file),
        )

        if result["feasible"]:
            # Row is feasible → ALL pairs in row are feasible and covered
            feasible_profiles.append(profile)

            feasible_pairs |= pairs_in_row   # logically feasible
            covered_pairs |= pairs_in_row    # and covered by an ST

        else:
            # Row infeasible → do NOT add its pairs to covered_pairs
            infeasible_profiles.append(profile)

            # NEW: call the new helper to find one infeasible pair
            _find_one_infeasible_pair_in_row(
                model_path=model_path,
                cfg=cfg,
                row=row,
                pairs_in_row=pairs_in_row,
                out_dir=out_dir,
                infeasible_pairs=infeasible_pairs,
                feasible_pairs=feasible_pairs,
                covered_pairs=covered_pairs,
            )


    # -------------------------------
    # PHASE 2 — DYNAMIC COMPLETION
    # -------------------------------

    rows_phase2: List[Row] = []

    def _pick_uncovered_pair() -> Optional[frozenset]:
        """Return one pair that is neither covered nor known infeasible, or None."""
        for p in all_required_pairs:
            if p not in covered_pairs and p not in infeasible_pairs:
                return p
        return None

    while True:
        target_pair = _pick_uncovered_pair()
        if target_pair is None:
            # All pairs are either covered (feasible) or known infeasible
            break

        # Try to build a row around this pair without using any known-infeasible pair
        row = _build_row_around_pair(
            target_pair=target_pair,
            names=names,
            doms=doms,
            infeasible_pairs=infeasible_pairs,
        )

        if row is None:
            # We couldn't find any completion for this pair without hitting a
            # known infeasible pair. In practice this means the target_pair
            # itself is effectively infeasible. Mark it and continue.
            infeasible_pairs.add(target_pair)
            continue

        profile = _profile_name_from_row(row)
        if profile in seen_profiles:
            # This should be rare; if it happens, just move to the next pair
            covered_pairs |= _pairs_for_row(row)
            continue

        seen_profiles.add(profile)
        trace_file = out_dir_path / f"run_{profile}.txt"

        global_index += 1
        pairs_in_row = _pairs_for_row(row)

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
            
            # Row exists → all its pairs are feasible
            feasible_pairs |= pairs_in_row
            covered_pairs |= pairs_in_row
            
        else:
            infeasible_profiles.append(profile)
            # Row infeasible → learn at least one infeasible pair from it
            _find_one_infeasible_pair_in_row(
                model_path=model_path,
                cfg=cfg,
                row=row,
                pairs_in_row=pairs_in_row,
                out_dir=out_dir,
                infeasible_pairs=infeasible_pairs,
                feasible_pairs=feasible_pairs,
                covered_pairs=covered_pairs,
            )

        rows_phase2.append(row)


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
        "feasible_pairs": feasible_pairs,
        "covered_pairs": covered_pairs,
        "infeasible_pairs": infeasible_pairs,
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
