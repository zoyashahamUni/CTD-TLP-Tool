# tool/ltl_builder.py
from __future__ import annotations
from typing import Dict, Union
from .config_schema import ToolConfig

Value = Union[bool, int]


def _expr_for_factor_value(name: str, value: Value) -> str:
    """
    Convert factor name + assigned value into an SMV expression
    referring to real model variables (Option B).
    """

    # a_logout_after_add
    if name == "a_no_logout_after_add":
        # True  → no logout after add      → no_logout_after_add = TRUE
        # False → logout happened after add → no_logout_after_add = FALSE
        return f"no_logout_after_add = {'TRUE' if value else 'FALSE'}"

    # b_max_items
    if name == "b_max_items":
        return f"max_items = {int(value)}"

    # c_no_remove
    if name == "c_no_remove":
        # True  → no remove ever happened → removed_ever = FALSE
        # False → a remove happened       → removed_ever = TRUE
        return f"removed_ever = {'FALSE' if value else 'TRUE'}"

    raise ValueError(f"Unknown factor name in LTL builder: {name!r}")


def build_ltl_for_row(cfg: ToolConfig, row: Dict[str, Value]) -> str:
    """
    Given a ToolConfig and one row (like {"a_no_logout_after_add": True, "b_max_items": 3, "c_no_remove": True}),
    build the complete LTL formula using cfg.ltl_template.
    """
    parts = []

    # 1) end_of_test flag
    parts.append(cfg.end_flag)

    # 2) Factor constraints mapped to real model variables
    for f in cfg.factors:
        name = f.name
        if name not in row:
            raise KeyError(f"Row missing value for factor {name!r}")
        v = row[name]
        expr = _expr_for_factor_value(name, v)
        parts.append(expr)

    inside = " & ".join(parts)

    return cfg.ltl_template.format(conditions=inside)
