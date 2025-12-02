CTD-TLP Tool — Usage Guide

This document explains how to install, configure, and run the CTD-TLP tool, including the requirements for Python, nuXmv, and the project file structure.

1. Prerequisites
Python

Python 3.8–3.12 recommended

Install dependencies (only standard library + nuXmv required)

nuXmv

Install nuXmv and make sure it is accessible from the command line:

macOS / Linux:

Download from:
https://nuxmv.fbk.eu/

Extract the folder.

Add to PATH:

export PATH="/path/to/nuXmv:$PATH"


Test the installation:

nuXmv -help

Windows:

Use the Windows release and make sure nuXmv.exe is in %PATH%.

2. Clone the Repository
git clone <your-github-url>
cd zoya-ctd-tool

3. Project Structure
tool/
  cli.py                - command line interface
  ipo_runner.py         - dynamic IPO + oracle algorithm
  ipo_oracle.py         - row/pair feasibility checks (with nuXmv)
  ltl_builder.py        - construct LTL formulas
  generator.py          - pairwise generator
  config_schema.py      - factors.json schema
  config_loader.py      - load/validate config

examples/
  shopping/
    model.smv           - running example model
    factors.json        - factor definitions

output_ipo/             - created automatically by the oracle

4. Prepare The Configuration
  The tool requires two files:
  1. `factors.json`

  Defines:

  factor names (A, B, C…), value domains, and the LTL template that is going to be used for the   CTD test row.

  Example:

  {
    "ltl_template": "F(end_of_test & {conditions})",
    "step_var": "step",
    "end_flag": "end_of_test",

    "factors": [
      { "name": "a_no_logout_after_add",  "values": [true, false]},
      { "name": "b_max_items",            "values": [3, 4, 5] },
      { "name": "c_no_remove",           "values": [true, false] }
    ]
  }
  **factor** - A logical property that is being tested.
  **values** - the domain of the factors. The type of the domain is being infered automatically   according to the values (meantime it is allowed to be Boolean anf Integers)
  **{conditions}** - is replaced with the factors values: (factor1 = v1) & (factor2 = v2) & ...


  2. `model.smv`

  The file must contain:

  **A step**
  step : {login, logout,add, remove, checkout, idle};

  **end_of_test**

  `end_of_test : boolean;`

  **State variables that are connected to the factors**
  no_logout_after_add : boolean;
  max_items           : 0..5;
  removed_ever        : boolean;

  **Optional mode variable**
  `mode : {LoggedOut, Shopping, CheckedOut};`
  It exists in the model but not a must by the tool.

5. Running the Tool
**Print normalized factor domains**
python -m tool.cli generate \
  --factors examples/shopping/factors.json \
  --print-rows

**Generate the pairwise rows**
python -m tool.cli generate \
  --factors examples/shopping/factors.json \
  --pairwise

**Print LTL formulas**
python -m tool.cli generate \
  --factors examples/shopping/factors.json \
  --pairwise --ltl

6. Running the Oracle (IPO + TLP)
**Full workflow:**
python -m tool.cli oracle-ipo \
  --model examples/shopping/model.smv \
  --factors examples/shopping/factors.json \
  --output-dir output_ipo


**This will:**

  1. Generate pairwise rows

  2. For each row: LTL formula and call nuXmv.

  3. Classify each row:

      - feasible - produces ST (test steps)

      - infeasible - with pair oracle check

  4. Continue generating new rows until:

      - all feasible pairs are covered

      - infeasible pairs are identified

**At the end, output directory contains:**

output_ipo/
  feasible.txt
  infeasible.txt
  run_A0_B3_C0.txt
  run_A1_B4_C0.txt
  ...


Each run_*.txt file contains the test steps (ST).

7. Frequent Errors & Troubleshooting
**Error: “Model contract missing variable ‘end_of_test’”**

Your SMV model must include:

end_of_test : boolean;

And a definition for next(end_of_test).

**Error: “predicate X not found in SMV model”**

Each factor name in factors.json has a real SMV variable in model.smv.

**Error: nuXmv not found"**

Run: `which nuXmv`

If empty: add nuXmv to PATH.

**Output folder empty**

Check the output folder path, permissions and nuXmv installation. 
For checking the output folder:

--output-dir <folder>

8. How to Add a New Model

To analyze a new system:

Copy your SMV file to `examples/<new_system>/model.smv`

Create matching `factors.json`

Run:

`python -m tool.cli generate --factors factors.json --pairwise`


And then:

`python -m tool.cli oracle-ipo --model model.smv --factors factors.json`


That’s all — the tool is model-independent as long as the contract is respected.

9. **Example for End-to-End Run**
python -m tool.cli oracle-ipo \
  --model examples/shopping/model.smv \
  --factors examples/shopping/factors.json \
  --output-dir output_ipo


Output summary:

Feasible profiles : 6
Infeasible profiles: 1
Infeasible pair found: A=TRUE, B=3