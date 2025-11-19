# tool/generator.py
from __future__ import annotations
from typing import List, Dict, Union, Tuple, Set, Any
from itertools import product
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
    for combo in product(*domains):
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

def _domains_from_factors(factors):
    """
    Convert ToolConfig.factors into a simple dict:
      name -> list of concrete values
    """
    doms: Dict[str, List[Any]] = {}
    for f in factors:
        # f.values already normalized (booleans as Python bool, ints as int)
        doms[f.name] = list(f.values or [])
    return doms


def _pairs_for_row(row: Dict[str, Any]):
    """
    Return all 2-way pairs from a row as frozensets:
      { (name1, val1), (name2, val2) }
    """
    pairs = set()
    names = sorted(row.keys())
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            n1, n2 = names[i], names[j]
            v1, v2 = row[n1], row[n2]
            pairs.add(frozenset(((n1, v1), (n2, v2))))
    return pairs


def generate_pairwise_twix(factors):
    """
    New IPO-style pairwise generator ("twix").

    Phase 1:
      - Work row-by-row on (A,B) and for each choose a C value
        that covers the most *new* pairs (A,C) and (B,C).
    Phase 2:
      - Compute all required 2-way pairs (over all factors).
      - While there are uncovered pairs, add rows that greedily
        cover the most remaining pairs (using full Cartesian product).
    """
    doms = _domains_from_factors(factors)
    names = [f.name for f in factors]

    if len(names) != 3:
        raise ValueError("generate_pairwise_twix currently assumes exactly 3 factors (A,B,C).")

    A, B, C = names  # keep order from factors.json
    rows: List[Dict[str, Any]] = []

    covered_pairs = set()

    # ---------- Phase 1: stream over all (A,B) combos and choose best C ----------
    for a_val in doms[A]:
        for b_val in doms[B]:
            best_c = None
            best_gain = -1

            # choose C that adds the most new pairs (A,C) and (B,C)
            for c_val in doms[C]:
                candidate_row = {A: a_val, B: b_val, C: c_val}
                pairs = _pairs_for_row(candidate_row)
                gain = sum(1 for p in pairs if p not in covered_pairs)
                if gain > best_gain:
                    best_gain = gain
                    best_c = c_val

            row = {A: a_val, B: b_val, C: best_c}
            rows.append(row)
            covered_pairs |= _pairs_for_row(row)

    # ---------- Phase 2: coverage completion ----------
    # All possible 2-way pairs over all factors:
    all_pairs = set()
    for r in product(*[doms[n] for n in names]):
        temp_row = dict(zip(names, r))
        all_pairs |= _pairs_for_row(temp_row)

    uncovered = all_pairs - covered_pairs

    # While there are still uncovered pairs, add rows that cover them greedily
    while uncovered:
        best_row = None
        best_gain = 0

        for r in product(*[doms[n] for n in names]):
            candidate = dict(zip(names, r))
            candidate_pairs = _pairs_for_row(candidate)
            gain = sum(1 for p in candidate_pairs if p in uncovered)
            if gain > best_gain:
                best_gain = gain
                best_row = candidate

        if best_row is None or best_gain == 0:
            # Should not happen for small domains, but safety escape
            break

        rows.append(best_row)
        covered_pairs |= _pairs_for_row(best_row)
        uncovered = all_pairs - covered_pairs

    return rows
