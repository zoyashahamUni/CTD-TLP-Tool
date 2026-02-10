
import json, subprocess, tempfile, os, re, random
from itertools import combinations
from pathlib import Path


# config files

MODEL_PATH = "examples/shopping/minimal_model.smv"
SETTINGS_PATH = "examples/shopping/settings.json"
OUTPUT_DIR = "output_traces"

#parse the output trace from nuXmv
STATE_RE = re.compile(r"^\s*->\s*State:")
ASSIGN_RE = re.compile(r"^\s*([A-Za-z0-9_]+)\s*=\s*(.+?)\s*$")
SPEC_VERDICT_RE = re.compile(
    r"^\s*--\s*specification\b.*\bis\s+(true|false)\b",
    re.IGNORECASE
)

def assert_balanced_parentheses(s: str):
    bal = 0
    for ch in s:
        if ch == '(':
            bal += 1
        elif ch == ')':
            bal -= 1
            if bal < 0:
                raise ValueError(f"Too many ')' in phi:\n{s}")
    if bal != 0:
        raise ValueError(f"Unbalanced parentheses (balance={bal}) in phi:\n{s}")

#read the settings.json and load as dictionary
def load_cfg(path):
    with open(path) as f:
        d = json.load(f)
    facs = {}

    for f in d["factors"]:
        name = f["name"]

        # Boolean factor: has a single LTL formula
        if "ltl" in f:
            base_ltl = f["ltl"]

            
                        
            facs[name] = {
                "name": name,
                "kind": "bool",
                "values": [False, True],
                "value_ltls": {
                    False: f"!({base_ltl})",
                    True: base_ltl,
                },
                # "smv_var": smv_var,
            }

        elif "values" in f:
            domain = []
            value_ltls = {}     

            for entry in f["values"]:
                if "value" not in entry or "ltl" not in entry:
                    raise ValueError(f"Factor {name!r} has a malformed values entry: {entry!r}")
                
                v = entry["value"]
                ltl = entry["ltl"]
                
                domain.append(v)
                value_ltls[v] = ltl

            facs[name] = {
                "name": name,
                "kind": "enum",
                "values": domain,      # e.g. [3,4,5]
                "value_ltls": value_ltls,
            }

        else:
            raise ValueError(
                f"Factor {name!r} must have either 'ltl' or 'values' in settings.json"
            )

    if "step_var" not in d:
        raise ValueError("Missing required 'step_var' in settings.json")
    
    return {
        "factors": facs,
        "end": d.get("end_flag"),
        "step_var": d["step_var"],
        "test_rule": d.get("test_rule", "TRUE")
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

# Keep the int values according to what was assigned in the settings.json
def end_domain_guard(cfg):
    return "TRUE"           

def phi_for_value(factor_name, value, cfg):
    fac = cfg["factors"][factor_name]
    return fac["value_ltls"][value]

def phi_for_row(row, cfg):
    """
    Build the LTL formula for a *full CTD row*:
    test_rule & guard & (AND over all factor value LTLs).
    """
    guard = end_domain_guard(cfg)          # currently "TRUE"
    test_rule = cfg.get("test_rule", "TRUE")
    end_flag = cfg.get("end")

    if end_flag:
        test_rule = test_rule.replace("end_flag", end_flag)

    # Conjunction of all factor-value formulas from settings.json
    ltl_parts = []
    for name, value in row.items():
        ltl_parts.append(f"({phi_for_value(name, value, cfg)})")

    core = " & ".join(ltl_parts) if ltl_parts else "TRUE"

    return f"(({test_rule}) & ({guard}) & ({core}))"

def phi_for_pair(pair, cfg):
    """
    Build the LTL formula for a single CTD pair (f1=v1, f2=v2),
    combined with the global test_rule.
    """
    (f1, v1), (f2, v2) = pair

    phi1 = cfg["factors"][f1]["value_ltls"][v1]
    phi2 = cfg["factors"][f2]["value_ltls"][v2]

    test_rule = cfg.get("test_rule", "TRUE")
    end_flag = cfg.get("end")

    if end_flag:
        test_rule = test_rule.replace("end_flag", end_flag)

    core = f"({phi1}) & ({phi2})"
    return f"(({test_rule}) & ({core}))"



#Run nuXmv as the oracle by sending the not(phi) and returning the counter example output if the row is feasible, if True is returned the pair is infeasible return None.
def run_nuxmv(model, phi, timeout_sec=30):
    assert_balanced_parentheses(phi)
    script = (
        f"read_model -i {model}\n"
        "go\n"
        f"check_ltlspec -p \"!( {phi} )\"\n"
        "show_traces -v\n"
        #"show_traces\n"
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

    current = {}
    pending = None
    
    for line in stdout.splitlines():
        if "<!-- ################### Trace number:" in line:
            break

        if STATE_RE.match(line):

            if pending is not None:
                current.update(pending)
                if step_var in current:
                    val = current[step_var].strip().strip('"').lower()
                    steps.append(val)
            pending = {}     # NEW: start collecting assignments for this state
            continue
        
        m = ASSIGN_RE.match(line)
        if m and pending is not None:
            pending[m.group(1)] = m.group(2).strip()

    if pending is not None:
        current.update(pending)
        if step_var in current:
            val = current[step_var].strip().strip('"').lower()
            steps.append(val)
    return steps
    
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

def test_row(row, cfg, model):
    """
    Ask nuXmv whether there exists a trace satisfying the full row assignment.
    Returns (is_feasible: bool, stdout).
    """
    phi = phi_for_row(row, cfg)
    status, out = run_nuxmv(model, phi)

    if status == "FEASIBLE":
        return True, out
    if status == "INFEASIBLE":
        return False, out

    raise RuntimeError(
        f"Unexpected nuXmv status {status!r} for row {row} with phi:\n{phi}\n\nOutput:\n{out}"
    )

def pair_is_feasible(pair, cfg, model):
    """
    Ask nuXmv whether there exists a trace satisfying a single pair (f1=v1, f2=v2).
    Returns True if the pair is feasible, False otherwise.
    """
    phi = phi_for_pair(pair, cfg)
    status, _ = run_nuxmv(model, phi)
    return (status == "FEASIBLE")

#Checks which pairs are covered by the row
def row_satisfies(row, pair):
    (f1, v1), (f2, v2) = pair
    return row.get(f1) == v1 and row.get(f2) == v2

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

def build_row_from_pair(pair, cfg):
    """
    TEMPORARY: build a full row that agrees with the given pair,
    and assigns a default value (first in domain) to all other factors.
    """
    (f1, v1), (f2, v2) = pair
    row = {f1: v1, f2: v2}
    for name, fac in cfg["factors"].items():
        if name in row:
            continue
        row[name] = fac["values"][0]
    return row

#Sets up the data structures that are needed to implement the algorithm
#It loads the configuration from settings.json
#using the todo list to check the pairs that appear there
#Either they'll be infeasible or feasible - in both cases they'll be removed from the todo. 
# If they're infeasible - they'll be moved to a specific list, so we'll not use them again while building the other rows
def gen_tests(model_path, settings_path):
    cfg = load_cfg(settings_path)
    pairs = all_pairs(cfg["factors"])
    todo = set(pairs)
    
    tests = []
    infeasible_pairs = set()
    infeasible_rows = set()
    seen_rows = set()

    while todo:
        pair = random.choice(tuple(todo))
        candidate_row = build_row_from_pair(pair, cfg)
        k = row_key(candidate_row)
        
        if k in infeasible_rows:
            todo.remove(pair)
            continue
        
        is_feasible_row, trace = test_row(candidate_row, cfg, model_path)
    
        if not is_feasible_row:
            row = candidate_row

            # Collect all pairs appearing in this row
            factor_names = sorted(cfg["factors"].keys())
            row_pairs = set()
            for i in range(len(factor_names)):
                for j in range(i + 1, len(factor_names)):
                    f1, f2 = factor_names[i], factor_names[j]
                    p = ((f1, row[f1]), (f2, row[f2]))
                    row_pairs.add(p)

            # Check with nuXmv which pairs are truly infeasible
            any_pair_infeasible = False
            for p in row_pairs:
                if p not in todo:
                    continue
                if not pair_is_feasible(p, cfg, model_path):
                    infeasible_pairs.add(p)
                    todo.remove(p)
                    any_pair_infeasible = True

            # If no pair is infeasible → this is a higher-order (3+ factors) infeasibility
            # Mark the row itself as infeasible so we do not revisit it.
            if not any_pair_infeasible:
                infeasible_rows.add(k)


            # In any case, do not add this row to tests
            continue

        # ----- Case: row is feasible -----
        row = candidate_row

        # If we have already produced this row, just remove any pairs it covers from todo
                
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


                
    feasible_pairs = pairs - infeasible_pairs
    tests = minimize_tests_greedy(tests, feasible_pairs)
    prune_output_files(tests)
                
    return tests, infeasible_pairs, pairs

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
