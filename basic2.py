
import json, subprocess, tempfile, os, re, random
from itertools import combinations
from pathlib import Path


# config files

MODEL_PATH = "examples/shopping/model.smv"
SETTINGS_PATH = "examples/shopping/settings.json"
OUTPUT_DIR = "output_traces"

#parse the output trace from nuXmv
STATE_RE = re.compile(r"^\s*-> State:")
ASSIGN_RE = re.compile(r"^\s*([A-Za-z0-9_]+)\s*=\s*(.+?)\s*$")
VAR_FROM_LTL_RE = re.compile(r"[FGX]\(\s*([A-Za-z_][A-Za-z0-9_]*)")
SPEC_VERDICT_RE = re.compile(
    r"^\s*--\s*specification\b.*\bis\s+(true|false)\b",
    re.IGNORECASE
)

#read the factors.json and load as dictionary
def load_cfg(path):
    with open(path) as f:
        d = json.load(f)
    facs = {}

    for f in d["factors"]:
        name = f["name"]

        # Prefer explicit smv_var from JSON; fall back to inference if missing
        explicit_smv_var = f.get("smv_var")

        # Boolean factor: has a single LTL formula
        if "ltl" in f:
            base_ltl = f["ltl"]

            # Use explicit smv_var if given, otherwise infer from LTL
            smv_var = explicit_smv_var
            if smv_var is None:
                # Try to extract the SMV variable from the LTL, assuming patterns like F(var) or F(var = 3)
                m = VAR_FROM_LTL_RE.search(base_ltl)
                smv_var = m.group(1) if m else None
            
            if smv_var is None:
                raise ValueError(
                    f"Cannot infer SMV variable name for factor {name!r} from LTL: {base_ltl!r}. "
                    "Expected patterns like F(var) or F(var = value)."
                )
                        
            facs[name] = {
                "name": name,
                "kind": "bool",
                # CTD domain:
                "values": [False, True],
                # For a boolean factor, the LTL for each value:
                "value_ltls": {
                    False: f"!({base_ltl})",
                    True: base_ltl,
                },
                "smv_var": smv_var,
            }

        # Enumerated factor: has "values": [ { "value": X, "ltl": "..." }, ... ]
        elif "values" in f:
            domain = []
            value_ltls = {}
            # Use explicit smv_var if given, otherwise infer from LTLs
            smv_var = explicit_smv_var            

            for entry in f["values"]:
                if "value" not in entry or "ltl" not in entry:
                    raise ValueError(f"Factor {name!r} has a malformed values entry: {entry!r}")
                
                v = entry["value"]
                ltl = entry["ltl"]
                
                domain.append(v)
                value_ltls[v] = ltl
                
                if smv_var is None:
                    m = VAR_FROM_LTL_RE.search(ltl)
                    if m:
                        smv_var = m.group(1)
                
            if smv_var is None:
                raise ValueError(
                    f"Cannot infer SMV variable name for factor {name!r} from any of its value LTLs. "
                    "Expected patterns like F(var = value)."
                )    

            facs[name] = {
                "name": name,
                "kind": "enum",
                "values": domain,      # e.g. [3,4,5]
                "value_ltls": value_ltls,
                "smv_var": smv_var,
            }

        else:
            raise ValueError(
                f"Factor {name!r} must have either 'ltl' or 'values' in factors.json"
            )

    if "step_var" not in d:
        raise ValueError("Missing required 'step_var' in factors.json")
    
    return {
        "factors": facs,
        "end": d.get("end_flag"),
        "step_var": d["step_var"],
        "test_flag": d.get("test_flag", "TRUE")
    }


#Create all the pairs combinations of the factor's values ((f1,v1),(f2,v2)...((fn-1,vn-1),(fn,vn))
def all_pairs(factors):
    names = list(factors)
    ps = set()
    for f1, f2 in combinations(names, 2):
        for v1 in factors[f1]["values"]:
            for v2 in factors[f2]["values"]:
                ps.add(((f1, v1), (f2, v2)))
    return ps

# Keep the int values according to what was assigned in the factors.json
def end_domain_guard(cfg):
    clauses = []
    for name, e in cfg["factors"].items():
        # Only guard enum/int-like factors (domain not purely boolean)
        vs = e["values"]
        if all(isinstance(v, bool) for v in vs):
            continue

        smv_var = e.get("smv_var")
        if smv_var is None:
            raise RuntimeError(f"Missing smv_var for factor {name!r}")

        # Build: (smv_var = v1) | (smv_var = v2) | ...
        disj = " | ".join(f"({smv_var} = {v})" for v in vs)
        clauses.append(f"({disj})")

    return "TRUE" if not clauses else " & ".join(clauses)

#Build the LTL property for a given CTD pair. The cfg is guidance of how to build the LTL phrase
def phi_for_pair(pair, cfg):
    (f1, v1), (f2, v2) = pair

    # factor LTLs characterize the trace
    phi1 = cfg["factors"][f1]["value_ltls"][v1]
    phi2 = cfg["factors"][f2]["value_ltls"][v2]

    guard = end_domain_guard(cfg)
    test_rule = cfg.get("test_rule", "TRUE")
    end_flag = cfg.get("end")

    if end_flag:
        test_rule = test_rule.replace("end_flag", end_flag)
        reach_extract = f"F(({end_flag} = TRUE) & ({guard}))"
    else:
        reach_extract = "TRUE"
    return f"({test_rule}) & ({reach_extract}) & ({phi1}) & ({phi2})"
    
#Run nuXmv as the oracle by sending the not(phi) and returning the counter example output if the row is feasible, if True is returned the pair is infeasible return None.
def run_nuxmv(model, phi, timeout_sec=30):
    script = (
        f"read_model -i {model}\n"
        "go\n"
        f"check_ltlspec -p \"!( {phi} )\"\n"
        "show_traces -v\n"
        "quit\n"                                #The script that runs the nuXmv
    )
    
    # make sure the temp file is cleaned
    with tempfile.NamedTemporaryFile("w", suffix=".cmd", delete=False) as f:
        f.write(script)
        cmd = f.name
    try:
        try:
            proc = subprocess.run(
                ["nuXmv", "-source", cmd],
                capture_output=True,
                text=True,
                timeout=timeout_sec
            )
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(
                f"nuXmv timed out after {timeout_sec} seconds for phi:\n{phi}"
            ) from e

        out = (proc.stdout or "") + "\n" + (proc.stderr or "")

        verdict = None
        for line in out.splitlines():
            m = SPEC_VERDICT_RE.match(line)
            if m:
                verdict = m.group(1).lower()

        if verdict == "false":
            return "FEASIBLE", out
        if verdict == "true":
            return "INFEASIBLE", out

        raise RuntimeError(
            f"Could not parse nuXmv verdict (neither true nor false) for phi:\n{phi}\n\n"
            f"Raw output:\n{out}"
        )

    finally:
        try:
            os.remove(cmd)
        except OSError:
            pass
            
def extract_steps(stdout, cfg):
    step_var = cfg["step_var"]
    steps = []

    state = {}
    for line in stdout.splitlines():
        if STATE_RE.match(line):
            if state and step_var in state:
                val = state[step_var].strip().strip('"').lower()
                steps.append(val)
            state = {}
            continue

        m = ASSIGN_RE.match(line)
        if m:
            state[m.group(1)] = m.group(2).strip()

    # finalize last state (end of output)
    if state and step_var in state:
        val = state[step_var].strip().strip('"').lower()
        steps.append(val)
    return steps

#Extract the row's factors when (phi) is feasible
def extract_row(stdout, cfg):
    end_flag = cfg["end"]           #may be None
    facs = cfg["factors"]

    state = {}
    last_any = None
    last_end = None
    
    for line in stdout.splitlines():    
        if STATE_RE.match(line):
            if state:
                last_any = state.copy()
                if end_flag is not None and state.get(end_flag) == "TRUE":
                    last_end = state.copy()
            state = {}
            continue            

        m = ASSIGN_RE.match(line)
        if m:
            state[m.group(1)] = m.group(2).strip()
    
    if state:
        last_any = state
        if end_flag is not None and state.get(end_flag) == "TRUE":
            last_end = state

    # Choose which state to use for reading the factor summary variables:
    # 1. If the model has an end_flag and we actually reached it, prefer that state.
    # 2. Otherwise, fall back to the last state we saw in the trace.
    if end_flag is not None and last_end is not None:
        last = last_end
    elif last_any is not None:
        last = last_any
    else:
        # No states at all in the trace → nothing to extract
        return None

    row = {}
    for name, e in facs.items():
        raw = last.get(e["smv_var"])
        if raw is None: 
            return None
        vs = e["values"]
        if all(isinstance(v, bool) for v in vs):
            value = (raw.upper() == "TRUE")
        else:
            value = int(raw) 

        allowed = set(vs)
        if value not in allowed:
            raise RuntimeError(
                f"Extracted value {value!r} for factor {name!r} "
                f"not in declared domain {sorted(allowed)}"
            )
        row[name] = value       
            
    return row                                  # The abstract CTD test - looks like a_no_logout_after_add: True, b_max_items: 4, c_no_remove: False 

#Files that are created to keep the traces for the test steps called in a name as: run_A0_B5_C1.txt
def filename_for_row(row):
    parts = []
    for name in sorted(row.keys()):
        letter = name[0].upper()
        value = row[name]
        num = 1 if value is True else 0 if value is False else value
        parts.append(f"{letter}{num}")
    return "run_" + "_".join(parts) + ".txt"


def row_key(row):
    return tuple(sorted(row.items()))


#save the trace of the row or just return
def save_steps(row, stdout, cfg, output_dir=OUTPUT_DIR):
    steps = extract_steps(stdout, cfg)
    if not steps:
        return

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    filename = filename_for_row(row)

    with open(out_dir / filename, "w") as f:
        for i, s in enumerate(steps, start=1):
            f.write(f"{i}. {s}\n")

def prune_output_files(chosen_tests, output_dir=OUTPUT_DIR):
    out_dir = Path(output_dir)
    if not out_dir.exists():
        return

    keep = {filename_for_row(t) for t in chosen_tests}

    for p in out_dir.glob("run_*.txt"):
        if p.name not in keep:
            try:
                p.unlink()
            except OSError:
                pass
            
#Runs nuXmv for a pair according to the model and calls the extract_row to figure out what is the entire set of factor values for this specific row
def test_for_pair(pair, cfg, model):
    status, out = run_nuxmv(model, phi_for_pair(pair, cfg))
    if status == "FEASIBLE":    
        row = extract_row(out, cfg)
        if row is None:
            raise RuntimeError("nuXmv returned a satisfying trace, but no parsable state was found.")
        return row, out
    if status == "INFEASIBLE":
        # explicitly infeasible pair
        return None, None

    # we should never get here with the current run_nuxmv implementation
    raise RuntimeError(
        f"Unexpected nuXmv status {status!r} for phi:\n{phi_for_pair(pair, cfg)}\n\nOutput:\n{out}"
    )

#Checks which pairs are covered by the row
def row_satisfies(row, pair):
    (f1, v1), (f2, v2) = pair
    return row[f1] == v1 and row[f2] == v2

def pairs_covered_by_row(row, all_pairs_set): 
    return {p for p in all_pairs_set if row_satisfies(row, p)}

def minimize_tests_greedy(tests, feasible_pairs):
    # Precompute coverage per test
    cov = [pairs_covered_by_row(t, feasible_pairs) for t in tests]

    remaining = set(feasible_pairs)
    chosen = []
    used = set()

    # Greedy pick: each time choose the test that covers most remaining pairs
    while remaining:
        best_i = None
        best_gain = set()

        for i, cset in enumerate(cov):
            if i in used:
                continue
            gain = cset & remaining
            if len(gain) > len(best_gain):
                best_gain = gain
                best_i = i

        if best_i is None:
            # Should not happen if tests truly cover feasible_pairs
            break

        used.add(best_i)
        chosen.append(tests[best_i])
        remaining -= best_gain

    return chosen


#Sets up the data structures that are needed to implement the algorithm
#It loads the configuration from factors.json
#using the todo list to check the pairs that appear there
#Either they'll be infeasible or feasible - in both cases they'll be removed from the todo. 
# If they're infeasible - they'll be moved to a specific list, so we'll not use them again while building the other rows
def gen_tests(model_path, settings_path):
    cfg = load_cfg(settings_path)
    pairs = all_pairs(cfg["factors"])
    todo = set(pairs)
    
    tests = []
    infeasible = set()
    seen_rows = set()

    while todo:
        pair = random.choice(tuple(todo))
        row, trace = test_for_pair(pair, cfg, model_path)

        #infeasible
        if row is None:
            infeasible.add(pair)
            todo.remove(pair)
            continue
        
        #feasible
        k = row_key(row)
        if k in seen_rows:
            # Row already produced; still remove covered pairs, but do not add a duplicate test / trace
            for p in list(todo):
                if row_satisfies(row, p):
                    todo.remove(p)
            continue
        
        seen_rows.add(k)
        tests.append(row)
        save_steps(row, trace, cfg)
        
        for p in list(todo):
            if row_satisfies(row, p):
                todo.remove(p)


                
    feasible_pairs = pairs - infeasible
    tests = minimize_tests_greedy(tests, feasible_pairs)
    prune_output_files(tests)
                
    return tests, infeasible, pairs

#The beginning
def main():
    model = str(Path(MODEL_PATH).resolve())
    settings = str(Path(SETTINGS_PATH).resolve())
    tests, infeasible, pairs = gen_tests(model, settings)        #tests = the generated CTD rows, 
    
    #Prints the tests that we need to run
    print("Generated tests:")
    for i,t in enumerate(tests, start=1):
        print(f" Test {i}: {t}")
    
    #Print the infeasible pairs
    print("\nInfeasible CTD pairs:")
    if infeasible:
        for p in infeasible:
            print(" ", p)
    else:
        print("  (none)")
    print(f"\nTotal CTD pairs:     {len(pairs)}")
    print(f"Feasible CTD pairs:  {len(pairs) - len(infeasible)}")
    print(f"Infeasible CTD pairs:{len(infeasible)}")

if __name__ == "__main__":
    main()
