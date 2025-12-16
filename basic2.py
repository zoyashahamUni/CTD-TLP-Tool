
import json, subprocess, tempfile, os, re, random
from itertools import combinations
from pathlib import Path


# config files

MODEL_PATH = "examples/shopping/model.smv"
FACTORS_PATH = "examples/shopping/factors.json"
OUTPUT_DIR = "output_traces"

#parse the output trace from nuXmv
STATE_RE = re.compile(r"^\s*-> State:")
ASSIGN_RE = re.compile(r"^\s*([A-Za-z0-9_]+)\s*=\s*(.+?)\s*$")
VAR_FROM_LTL_RE = re.compile(r"[FGX]\(\s*([A-Za-z_][A-Za-z0-9_]*)")

#read the factors.json and load as dictionary
def load_cfg(path):
    with open(path) as f:
        d = json.load(f)
    facs = {}

    for f in d["factors"]:
        name = f["name"]

        # Boolean factor: has a single LTL formula
        if "ltl" in f:
            base_ltl = f["ltl"]

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
            smv_var = None

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

    return {
        "factors": facs,
        "end": d["end_flag"],
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


def end_state_cond(name, val, cfg):
    e = cfg["factors"][name]
    smv_var = e["smv_var"]

    if smv_var is None:
        raise RuntimeError(f"Missing smv_var for factor {name!r}")

    if isinstance(val, bool):
        v = "TRUE" if val else "FALSE"
        return f"({smv_var} = {v})"
    else:
        return f"({smv_var} = {val})"


#Build the LTL property for a given CTD pair. The cfg is guidance of how to build the LTL phrase
def phi_for_pair(pair, cfg):
    (f1, v1), (f2, v2) = pair
    end = cfg["end"]

    phi1_at_end = end_state_cond(f1, v1, cfg)
    phi2_at_end = end_state_cond(f2, v2, cfg)

    # Require: there exists a future state where end_flag is TRUE AND
    # the selected factor-values hold in THAT SAME end state.
    guard = end_domain_guard(cfg)
    return f"F(({end} = TRUE) & ({guard}) & ({phi1_at_end}) & ({phi2_at_end}))"
#Run nuXmv as the oracle by sending the not(phi) and returning the counter example output if the row is feasible, if True is returned the pair is infeasible return None.
def run_nuxmv(model, phi):
    script = f"read_model -i {model}\ngo\ncheck_ltlspec -p \"!( {phi} )\"\nshow_traces -v\nquit\n" #The script that runs the nuXmv
    
    # make sure the temp file is cleaned
    with tempfile.NamedTemporaryFile("w", suffix=".cmd", delete=False) as f:
        f.write(script)
        cmd = f.name
    try:
        #for cleanup consistency using the Path
        out = subprocess.run(["nuXmv", "-source", cmd],
                             capture_output=True, text=True).stdout
    finally:
        try: os.remove(cmd)
        except OSError: pass
    return out if "is false" in out else None

#Extract the row's factors when (phi) is feasible
def extract_row(stdout, cfg):
    end_flag = cfg["end"]
    facs = cfg["factors"]
    state, last = {}, None
    for line in stdout.splitlines():
        if STATE_RE.match(line):
            if state.get(end_flag) == "TRUE":
                last = state.copy()
            state = {}
            continue
        m = ASSIGN_RE.match(line)
        if m:
            state[m.group(1)] = m.group(2).strip()
    if state.get(end_flag) == "TRUE":           #you reached the end of the Trace (test steps)
        last = state
    if last is None:
        return None                             # it didn't end
    row = {}
    for name, e in facs.items():
        raw = last.get(e["smv_var"])
        if raw is None: return None
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
def save_trace(row, trace, output_dir=OUTPUT_DIR):
    if trace is None:
        return

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = filename_for_row(row)

    # split trace into lines
    lines = trace.splitlines()

    # keep only the part after the "Trace number" marker
    for i, line in enumerate(lines):
        if "<!-- ################### Trace number" in line:
            lines = lines[i+1:]
            break    

    with open(out_dir / filename, "w") as f:            #write the cleaned trace to a file
        f.write("\n".join(lines) + "\n")

#Runs nuXmv for a pair according to the model and calls the extract_row to figure out what is the entire set of factor values for this specific row
def test_for_pair(pair, cfg, model):
    out = run_nuxmv(model, phi_for_pair(pair, cfg))
    if not out:
        return None, None
    
    row = extract_row(out, cfg)
    if row is None:
        raise RuntimeError(
            "nuXmv returned a satisfying trace, but no state with end_flag=TRUE was found. "
        )
    return row, out

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
def gen_tests(model_path, factors_path):
    cfg = load_cfg(factors_path)
    pairs = all_pairs(cfg["factors"])
    todo = set(pairs)
    tests, infeasible = [], set()
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
        save_trace(row, trace)
        for p in list(todo):
            if row_satisfies(row, p):
                todo.remove(p)
                
                
    covered = set()
    for row in tests:
        for p in pairs:
            if row_satisfies(row, p):
                covered.add(p)

    contradictions = infeasible & covered
    if contradictions:
        raise RuntimeError(f"Infeasible pairs covered by generated tests: {contradictions}")            
                
    feasible_pairs = pairs - infeasible
    tests = minimize_tests_greedy(tests, feasible_pairs)

                
    return tests, infeasible, pairs

#The beginning
def main():
    model = str(Path(MODEL_PATH).resolve())
    factors = str(Path(FACTORS_PATH).resolve())
    tests, infeasible, pairs = gen_tests(model, factors)        #tests = the generated CTD rows, 
    
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
