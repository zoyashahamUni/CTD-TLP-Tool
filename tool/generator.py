# tool/generator.py
from __future__ import annotations
from typing import List, Dict, Union, Tuple, Set
import itertools
from .config_schema import Factor


Value = Union[bool, int]
Row = Dict[str, Value]

def generate_full_combinations(factors: List[Factor]) -> List[Row]:
    """
    Generate the full Cartesian product of all factor domains.
    Returns a list of rows, each row is {factor_name: value}.
    """
    if not factors:
        return []

    domains: List[List[Value]] = []
    names: List[str] = []

    for f in factors:
        names.append(f.name)
        vals = f.values or []
        if not vals:
            # Shouldn't happen with our schema, but guard anyway
            return []
        domains.append(vals)

    rows: List[Row] = []
    for combo in itertools.product(*domains):
        row = {name: value for name, value in zip(names, combo)}
        rows.append(row)
    return rows

def generate_pairwise(factors: List[Factor]) -> List[Row]:
    """
    Greedy set-cover over the full Cartesian product to cover all factor-value PAIRS.
    """
    if not factors:
        return []

    # Build domains and names
    names: List[str] = [f.name for f in factors]
    domains: List[List[Value]] = [list(f.values or []) for f in factors]

    # Universe of required pairs: ((i, val_i), (j, val_j)) with i<j
    def all_pairs() -> Set[Tuple[Tuple[int, Value], Tuple[int, Value]]]:
        U: Set[Tuple[Tuple[int, Value], Tuple[int, Value]]] = set()
        for i in range(len(factors)):
            for j in range(i + 1, len(factors)):
                for vi in domains[i]:
                    for vj in domains[j]:
                        U.add(((i, vi), (j, vj)))
        return U

    uncovered = all_pairs()
    if not uncovered:
        return []

    # All candidate rows = full product
    candidates: List[Row] = []
    for combo in __import__("itertools").product(*domains):
        candidates.append({names[k]: combo[k] for k in range(len(names))})

    selected: List[Row] = []

    # Greedy: pick the row that covers the most uncovered pairs, iterate
    while uncovered:
        best_row = None
        best_covers = 0
        best_covered_pairs: Set[Tuple[Tuple[int, Value], Tuple[int, Value]]] = set()

        for row in candidates:
            # Which pairs would this row cover?
            covered_now: Set[Tuple[Tuple[int, Value], Tuple[int, Value]]] = set()
            # compute indices->values for this row
            vals = [row[n] for n in names]
            for i in range(len(names)):
                for j in range(i + 1, len(names)):
                    pair = ((i, vals[i]), (j, vals[j]))
                    if pair in uncovered:
                        covered_now.add(pair)

            if len(covered_now) > best_covers:
                best_covers = len(covered_now)
                best_row = row
                best_covered_pairs = covered_now

        # Safety: if no progress (shouldn't happen), break to avoid infinite loop
        if best_row is None or best_covers == 0:
            break

        selected.append(best_row)
        uncovered -= best_covered_pairs

        # Optional micro-pruning: remove duplicate rows from candidates
        candidates = [r for r in candidates if r is not best_row]

    return selected
