# tool/config_schema.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional, Union, Dict, Any
import re

# ----------------------------
# Public dataclasses (used by loader & CLI)
# ----------------------------

FactorKind = Literal["boolean", "integer"]

_NAME_RX = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

@dataclass(frozen=True)
class Factor:
    """
    A CTD factor definition.
    - kind 'boolean': values are implicitly [False, True]
    - kind 'integer': 'values' must be a non-empty list of ints (domain)
    """
    name: str
    kind: FactorKind
    values: Optional[List[Union[bool, int]]] = None

    def normalized(self) -> "Factor":
        if not _NAME_RX.match(self.name):
            raise ValueError(f"Invalid factor name '{self.name}'. Use [A-Za-z_][A-Za-z0-9_]*")

        if self.kind == "boolean":
            # Always normalize to explicit boolean domain
            return Factor(name=self.name, kind="boolean", values=[False, True])

        if self.kind == "integer":
            if self.values is None or len(self.values) == 0:
                raise ValueError(f"Integer factor '{self.name}' must provide a non-empty 'values' list")
            # de-dup + sort + type check
            try:
                vals = sorted({int(v) for v in self.values})
            except Exception as e:
                raise ValueError(f"Integer factor '{self.name}' has non-integer values") from e
            return Factor(name=self.name, kind="integer", values=vals)

        raise ValueError(f"Unknown factor kind '{self.kind}' for '{self.name}'")


@dataclass(frozen=True)
class ToolConfig:
    """
    Normalized tool configuration.
    """
    factors: List[Factor] = field(default_factory=list)
    ltl_template: str = "F({factor}={value})"
    step_var: str = "step"
    mode_var: str = "mode"
    end_flag: str = "end_of_test"

    def factor_names(self) -> List[str]:
        return [f.name for f in self.factors]


# ----------------------------
# Validation / construction helpers
# ----------------------------

def _coerce_factor(raw: Dict[str, Any]) -> Factor:
    name = raw.get("name")
    values = raw.get("values")

    # 1) Basic checks
    if not isinstance(name, str):
        raise ValueError("Each factor must have a string 'name'")
    if not isinstance(values, list) or not values:
        raise ValueError(f"Factor '{name}': 'values' must be a non-empty list")

    # 2) Try to read explicit kind/type (backwards compatibility)
    kind = raw.get("type") or raw.get("kind")

    # 3) If kind is not provided → infer from values
    if kind is None:
        # All booleans → boolean factor
        if all(isinstance(v, bool) for v in values):
            kind = "boolean"
        # All ints (but not bool – since bool is a subclass of int in Python)
        elif all(isinstance(v, int) and not isinstance(v, bool) for v in values):
            kind = "integer"
        else:
            raise ValueError(
                f"Factor '{name}': cannot infer kind from values {values!r}. "
                "Use consistent booleans or integers, or specify 'kind'."
            )

    # 4) Validate kind
    if kind not in ("boolean", "integer"):
        raise ValueError(f"Factor '{name}': 'type'/'kind' must be 'boolean' or 'integer'")

    # 5) Build normalized Factor
    fac = Factor(name=name, kind=kind, values=values)
    return fac.normalized()

def validate_and_build_config(raw: Dict[str, Any]) -> ToolConfig:
    """
    Validate a raw dict (e.g., parsed from JSON) into a normalized ToolConfig.
    Required: 'factors' list
    Optional: 'ltl_template', 'step_var', 'mode_var', 'end_flag'
    """
    if not isinstance(raw, dict):
        raise ValueError("Config must be a JSON object")

    # Factors
    raw_factors = raw.get("factors")
    if not isinstance(raw_factors, list) or len(raw_factors) == 0:
        raise ValueError("'factors' must be a non-empty list")

    factors = [_coerce_factor(f) for f in raw_factors]

    # Check duplicates
    names = [f.name for f in factors]
    if len(names) != len(set(names)):
        dupes = [n for n in names if names.count(n) > 1]
        raise ValueError(f"Duplicate factor names: {sorted(set(dupes))}")

    # Optional fields with defaults
    ltl_template = raw.get("ltl_template", "F({factor}={value})")
    step_var     = raw.get("step_var", "step")
    mode_var     = raw.get("mode_var", "mode")
    end_flag     = raw.get("end_flag", "end_of_test")

    # Basic identifier validation for interface vars
    for label, var in (("step_var", step_var), ("mode_var", mode_var), ("end_flag", end_flag)):
        if not isinstance(var, str) or not _NAME_RX.match(var):
            raise ValueError(f"Invalid {label} '{var}'. Use [A-Za-z_][A-Za-z0-9_]*")

    return ToolConfig(
        factors=factors,
        ltl_template=str(ltl_template),
        step_var=str(step_var),
        mode_var=str(mode_var),
        end_flag=str(end_flag),
    )
