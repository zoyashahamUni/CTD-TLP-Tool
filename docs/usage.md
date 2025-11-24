CTD-TLP Tool — Usage Guide

This document explains how to install, configure, and run the CTD-TLP tool, including the requirements for Python, nuXmv, and the project file structure.

1. Prerequisites
✔ Python

Python 3.8–3.12 recommended

Install dependencies (only standard library + nuXmv required)

✔ nuXmv

You must install nuXmv and ensure it is accessible from the command line:

macOS / Linux:

Download from:
https://nuxmv.fbk.eu/

Extract the folder.

Add to PATH:

export PATH="/path/to/nuXmv:$PATH"


Test:

nuXmv -help

Windows:

Use the Windows release and ensure nuXmv.exe is in %PATH%.

2. Clone the Repository
git clone <your-github-url>
cd zoya-ctd-tool

3. Project Structure
tool/
  cli.py                → command line interface
  ipo_runner.py         → dynamic IPO + oracle algorithm
  ipo_oracle.py         → row/pair feasibility checks (nuXmv)
  ltl_builder.py        → construct LTL formulas
  generator.py          → Twix pairwise generator
  config_schema.py      → factors.json schema
  config_loader.py      → load/validate config

examples/
  shopping/
    model.smv           → running example model
    factors.json        → CTD factor definitions

output_ipo/             → created automatically by oracle

4. Preparing Your Configuration
The tool requires two files:
1. factors.json

Defines:

factor names (A, B, C…)

domains (boolean or integer)

mapping to predicates inside the SMV model

Example:

[
  { "name": "a_no_logout_after_add", "kind": "boolean" },
  { "name": "b_max_items",           "kind": "integer", "values": [3, 4, 5] },
  { "name": "c_no_remove",           "kind": "boolean" }
]

2. model.smv

Must contain:

mode

step

end_of_test

predicates corresponding to the factors

Model must end with:

INVAR end_of_test -> (some condition)

5. Running the Tool
✔ Print normalized factor domains
python -m tool.cli generate \
  --factors examples/shopping/factors.json \
  --print-rows

✔ Generate the Twix pairwise rows
python -m tool.cli generate \
  --factors examples/shopping/factors.json \
  --pairwise

✔ Print LTL formulas for each row
python -m tool.cli generate \
  --factors examples/shopping/factors.json \
  --pairwise --ltl

6. Running the Oracle (Dynamic IPO + TLP)
Full workflow:
python -m tool.cli oracle-ipo \
  --model examples/shopping/model.smv \
  --factors examples/shopping/factors.json \
  --output-dir output_ipo


This will:

Generate pairwise rows (phase 1)

Call nuXmv for each row

Classify each row:

feasible → produces ST (test steps)

infeasible → triggers pair-level checks

Continue generating new rows until:

all feasible pairs are covered

infeasible pairs are identified

At the end, output directory contains:

output_ipo/
  feasible.txt
  infeasible.txt
  run_A0_B3_C0.txt
  run_A1_B4_C0.txt
  ...


Each run_*.txt file contains the test steps (ST).

7. Frequent Errors & Troubleshooting
❌ Error: “Model contract missing variable ‘end_of_test’”

Your SMV model must include:

end_of_test : boolean;


And a definition for next(end_of_test).

❌ Error: “predicate X not found in SMV model”

Ensure that each factor name in factors.json has a matching predicate in model.smv.

❌ Error: nuXmv cannot be executed

Check:

which nuXmv


If empty: add nuXmv to PATH.

❌ Output folder empty

Check permissions and ensure:

--output-dir <folder>


exists or can be created.

8. How to Add a New Model

To integrate a new system model:

Copy your SMV file to examples/<new_system>/model.smv

Create matching factors.json

Run:

python -m tool.cli generate --factors factors.json --pairwise


Run:

python -m tool.cli oracle-ipo --model model.smv --factors factors.json


That’s all — the tool is model-independent as long as the contract is respected.

9. Example End-to-End Run
python -m tool.cli oracle-ipo \
  --model examples/shopping/model.smv \
  --factors examples/shopping/factors.json \
  --output-dir output_ipo


Output summary:

Feasible profiles : 6
Infeasible profiles: 1
Infeasible pair found: A=TRUE, B=3