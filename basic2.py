"""
The script finds feasible a small set of feasible tests based on CTD algorithm (pairwise) while using the nuXmv model as the oracle. 
It generates LTL formula based each time on different pair as the basis of the algorithm in order to cover all pairs. 
How the tool is working: 
1. The tool reads two files: factors.json and model.smv 
- factors.json - includes which factors exist in the system and how the LTL formula is going to be generated. 
- model.smv - The set of rules that exist in our testing system. 
Each **factor** is a testing dimension. 
In the SMV model each factor is represented by implementing the state variables, 
their value in the final state summarizes some temporal behavior for the whole test,
For example - "no logout after add while items>0" or "the maximum number of items that was seen during the run" etc. 
- the LTL formula that is passed to the nuXmv has the structure defined in factors.json: F(end_of_test & factor1=value1 & factor2=value2 & ...) 
Which means that the temporal aspect is encoded in the SMV transition relation, 
The LTL checks whether there is a complete test whose final summary variables match this CTD row. 
2. The system creates all pairs of the factors' values. The set of uncovered pairs is called "todo" 
e.g. - if there are 3 factors:a,b,c val(a)= {0,1}, val(b)={3,4,5} val(c) = {0,1}. 
There will be a full list of all the values of the following factors combinations: (a,b), (b,c), (a,c). 
The todo list is: (a.0, b.3), (a.0, b.4) ... (a.0,c.0)....(b.3, c.0)....(b.5,c.1) 
3. While the todo list is not empty: 
    1. Pick randomly one pair (u,v) from the list "todo": 
        //1.1 generate factors (u', v') from (u,v) 
        1.2 construct the LTL formula phi=F(...) 
    2. Ask nuXmv oracle if there is a trace in the FSM that satisfies phi, 
    (actually it is sent as !(phi) and the nuXmv returns a counterexample that satisfies (phi) if it is feasible or none if there is no such trace)
        1. If no - the pair (u',v') will be marked as infeasible and will be removed from the list "todo" 
        2. If yes - 
            1. the oracle returns the trace W. Note that W is a sequence of ST (test steps). Save W as a trace file in the output_traces folder. 
            2. Let t be the final state in the trace W. Note that t contains the full row's factors' values, (specifically for factors that are different from (u',v'). 
            //3. Let list_t be the list of all the pairs of factors' values that appear in t. 
            3. For each remaining pair in todo, check whether t satisfies it.
            4. Remove from the "todo" all the pairs that t satisfies. 
            5. print all generated feasible rows after the loop ends.
            
At the end the algorithm creates the output_traces folder which contains one trace per generated test, 
such that every feasible pair of factor values is "covered" by at least one trace from this folder. 
Naturally we hope to have as few tests (and trace files) as possible.
"""
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

#read the factors.json 
def load_cfg(path):
    with open(path) as f:
        d = json.load(f)
    return {
        "factors": {x["name"]: x for x in d["factors"]},
        "tmpl": d["ltl_template"],
        "end": d["end_flag"],
    }

#Create all the CTD pairs combinations of the factor values
def all_pairs(factors):
    names = list(factors)
    ps = set()
    for f1, f2 in combinations(names, 2):
        for v1 in factors[f1]["values"]:
            for v2 in factors[f2]["values"]:
                ps.add(((f1, v1), (f2, v2)))
    return ps

#Build the individual factor constraint to use in phi_for_pair
def cond(name, val, cfg):
    e = cfg["factors"][name]
    v = "TRUE" if val is True else "FALSE" if val is False else str(val)
    return f"({e['smv_var']} = {v})"

#Build the LTL property for a given CTD pair
def phi_for_pair(pair, cfg):
    (f1, v1), (f2, v2) = pair
    
    cond1 = cond(f1, v1, cfg)
    cond2 = cond(f2, v2, cfg)
    joined = f"({cond1}) & ({cond2})"
    return cfg["tmpl"].replace("{conditions}", joined)
    
    # cs = [cond(f1, v1, cfg), cond(f2, v2, cfg)]
    # To use only the integer values we declared we want to test in the factors.json file
    # for name, e in cfg["factors"].items():
    #     vs = e["values"]
    #     if vs and all(isinstance(x, int) and not isinstance(x, bool) for x in vs):
    #         d = " | ".join(f"{e['smv_var']} = {x}" for x in vs)
    #         cs.append(f"({d})")
    # joined = " & ".join(f"({c})" for c in cs)
    # return cfg["tmpl"].replace("{conditions}", joined)

#Call nuXmv with the not(generated LTL property) and return the counter example output which means that the row is feasible
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

#Extract the entire set of factor values that exist when end_State==True
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
    if state.get(end_flag) == "TRUE":
        last = state
    if last is None:
        return None
    row = {}
    for name, e in facs.items():
        raw = last.get(e["smv_var"])
        if raw is None: return None
        vs = e["values"]
        if all(isinstance(v, bool) for v in vs):
            row[name] = (raw.upper() == "TRUE")
        else:
            row[name] = int(raw)
    return row
#Files that are created to keep the traces for runnin test steps
def filename_for_row(row):
    parts = []
    for name in sorted(row.keys()):
        letter = name[0].upper()
        value = row[name]
        num = 1 if value is True else 0 if value is False else value
        parts.append(f"{letter}{num}")
    return "run_" + "_".join(parts) + ".txt"


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

    with open(out_dir / filename, "w") as f:
        f.write("\n".join(lines) + "\n")

#Runs nuXmv for a pair according to the model and calls the extract_row to figure out what is the entire set of factor values for this specific row
def test_for_pair(pair, cfg, model):
    out = run_nuxmv(model, phi_for_pair(pair, cfg))
    if not out:
        return None, None
    row = extract_row(out, cfg)
    return row, out

#Checks if a rest row satisfies the given CTD pair
def row_satisfies(row, pair):
    (f1, v1), (f2, v2) = pair
    return row[f1] == v1 and row[f2] == v2

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
    while todo:
        pair = random.choice(tuple(todo))
        row, trace = test_for_pair(pair, cfg, model_path)
        if row is None:
            infeasible.add(pair)
            todo.remove(pair)
            continue
        tests.append(row)
        save_trace(row, trace)
        for p in list(todo):
            if row_satisfies(row, p):
                todo.remove(p)
    return tests, infeasible, pairs

#The beginning
def main():
    model = str(Path(MODEL_PATH).resolve())
    factors = str(Path(FACTORS_PATH).resolve())
    tests, infeasible, pairs = gen_tests(model, factors)
    
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
